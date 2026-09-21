import asyncio, hashlib, html, logging, shutil, tempfile, uuid, zipfile
from pathlib import Path
from aiogram import Bot, Dispatcher, F, Router
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, FSInputFile, Message
from .archive import UnsafeArchive, extract_zip_safely
from .build_logic import BuildPlan, detect_build, workflow
from .config import load_settings
from .db import Database, Upload
from .github_api import GitHubClient, GitHubError
from .keyboards import back, main_menu, manual, mode
from .middleware import AccessMiddleware
from .security import TokenVault

logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(name)s: %(message)s")
log=logging.getLogger("builder")
router=Router(); settings=None; bot=None; db=None; vault=None; tasks=set()

class Connect(StatesGroup): username=State(); token=State()
class UploadState(StatesGroup): archive=State()
class ManualState(StatesGroup): commands=State(); file=State()

async def show_menu(target,text="Выберите действие:"):
    connected=await db.get_account(target.from_user.id) is not None
    if isinstance(target,CallbackQuery): await target.message.edit_text(text,reply_markup=main_menu(connected)); await target.answer()
    else: await target.answer(text,reply_markup=main_menu(connected))

@router.message(CommandStart())
async def start(m:Message,state:FSMContext): await state.clear(); await show_menu(m,"<b>GitHub Builder v2</b>\n\nАвтоматическая или ручная сборка JAR/APK.")
@router.callback_query(F.data=="menu:home")
async def home(c:CallbackQuery,state:FSMContext): await state.clear(); await show_menu(c)
@router.callback_query(F.data=="menu:help")
async def help_page(c:CallbackQuery):
    await c.message.edit_text("<b>Режимы</b>\n\n⚡ <b>Автоматически</b> — бот ищет <code>build</code>, <code>build.sh</code>, <code>gradlew</code>, <code>build.gradle(.kts)</code>, <code>mvnw</code> или <code>pom.xml</code>.\n\n🛠 <b>Вручную</b> — отправьте shell-команды текстом либо файл build/build.sh/build.gradle/build.gradle.kts/pom.xml.\n\nРезультатом должен быть .jar или .apk.",reply_markup=back()); await c.answer()

@router.callback_query(F.data=="menu:connect")
async def connect(c:CallbackQuery,state:FSMContext): await state.set_state(Connect.username); await c.message.edit_text("Введите логин GitHub:",reply_markup=back()); await c.answer()
@router.message(Connect.username,F.text)
async def username(m:Message,state:FSMContext):
    name=m.text.strip().lstrip("@"); await state.update_data(username=name); await state.set_state(Connect.token); await m.answer("Отправьте GitHub classic PAT с правами <code>repo</code> и <code>workflow</code>. Сообщение будет удалено.")
@router.message(Connect.token,F.text)
async def token(m:Message,state:FSMContext):
    value=m.text.strip()
    try: await m.delete()
    except Exception: pass
    status=await m.answer("Проверяю GitHub…"); entered=(await state.get_data()).get("username",""); gh=GitHubClient(value)
    try:
        actual=await gh.whoami()
        if actual.casefold()!=entered.casefold(): raise ValueError("Токен принадлежит аккаунту "+actual)
        await db.save_account(m.from_user.id,actual,vault.encrypt(value)); await state.clear(); await status.edit_text("✅ GitHub <b>"+html.escape(actual)+"</b> подключён.",reply_markup=main_menu(True))
    except Exception as exc: await state.clear(); await status.edit_text("❌ Не удалось подключить GitHub: <code>"+html.escape(str(exc)[:400])+"</code>",reply_markup=back())
    finally: await gh.close()
@router.callback_query(F.data=="menu:disconnect")
async def disconnect(c:CallbackQuery,state:FSMContext): await db.delete_account(c.from_user.id); await state.clear(); await c.message.edit_text("GitHub отключён.",reply_markup=main_menu(False)); await c.answer()

@router.callback_query(F.data=="menu:upload")
async def upload_start(c:CallbackQuery,state:FSMContext):
    if not await db.get_account(c.from_user.id): await c.answer("Сначала подключите GitHub",show_alert=True); return
    await state.set_state(UploadState.archive); await c.message.edit_text(f"Отправьте ZIP проекта, максимум {settings.max_archive_mb} МБ.",reply_markup=back()); await c.answer()
@router.message(UploadState.archive,F.document)
async def upload_receive(m:Message,state:FSMContext):
    doc=m.document; name=doc.file_name or "project.zip"
    if not name.lower().endswith(".zip"): await m.answer("Нужен ZIP-архив."); return
    if doc.file_size and doc.file_size>settings.max_archive_mb*1024*1024: await m.answer("Архив слишком большой."); return
    uid=uuid.uuid4().hex[:12]; path=settings.uploads_dir/(uid+".zip"); await bot.download(doc,destination=path); digest=hashlib.sha256(path.read_bytes()).hexdigest()
    await db.save_upload(Upload(uid,m.from_user.id,name,str(path),path.stat().st_size,digest)); await state.clear()
    await m.answer("✅ Архив загружен.\n\nВыберите способ сборки:",reply_markup=mode(uid))
@router.message(UploadState.archive)
async def need_zip(m:Message): await m.answer("Отправьте ZIP как документ.")

@router.callback_query(F.data.startswith("choose:"))
async def choose_again(c:CallbackQuery): uid=c.data.split(":",1)[1]; await c.message.edit_text("Выберите способ сборки:",reply_markup=mode(uid)); await c.answer()
@router.callback_query(F.data.startswith("manual:"))
async def manual_menu(c:CallbackQuery): uid=c.data.split(":",1)[1]; await c.message.edit_text("Как задать ручную сборку?",reply_markup=manual(uid)); await c.answer()
@router.callback_query(F.data.startswith("auto:"))
async def auto_build(c:CallbackQuery): await begin_build(c,c.data.split(":",1)[1],"auto",None,None)
@router.callback_query(F.data.startswith("manualtext:"))
async def manual_text(c:CallbackQuery,state:FSMContext):
    uid=c.data.split(":",1)[1]; await state.update_data(upload_id=uid); await state.set_state(ManualState.commands); await c.message.edit_text("Отправьте shell-команды одним сообщением. Пример:\n<pre>chmod +x gradlew\n./gradlew build</pre>",reply_markup=back()); await c.answer()
@router.message(ManualState.commands,F.text)
async def manual_commands(m:Message,state:FSMContext):
    commands=m.text.strip(); data=await state.get_data(); await state.clear()
    if not commands or len(commands)>12000: await m.answer("Команды пустые или длиннее 12000 символов."); return
    await begin_build_message(m,data["upload_id"],"manual-text",commands,None)
@router.callback_query(F.data.startswith("manualfile:"))
async def manual_file_start(c:CallbackQuery,state:FSMContext):
    uid=c.data.split(":",1)[1]; await state.update_data(upload_id=uid); await state.set_state(ManualState.file); await c.message.edit_text("Отправьте build-файл до 128 КБ: build, build.sh, build.gradle, build.gradle.kts, pom.xml либо текстовый shell-скрипт.",reply_markup=back()); await c.answer()
@router.message(ManualState.file,F.document)
async def manual_file_receive(m:Message,state:FSMContext):
    if m.document.file_size and m.document.file_size>128*1024: await m.answer("Файл больше 128 КБ."); return
    temp=settings.uploads_dir/("script-"+uuid.uuid4().hex); await bot.download(m.document,destination=temp)
    try: content=temp.read_text(encoding="utf-8")
    except UnicodeDecodeError: temp.unlink(missing_ok=True); await m.answer("Файл должен быть текстовым UTF-8."); return
    temp.unlink(missing_ok=True); data=await state.get_data(); await state.clear(); await begin_build_message(m,data["upload_id"],"manual-file",content,m.document.file_name or "build.sh")

async def begin_build(c:CallbackQuery,upload_id,build_mode,commands,filename):
    up=await db.get_upload(upload_id,c.from_user.id); account=await db.get_account(c.from_user.id)
    if not up or not account: await c.answer("Архив или GitHub не найден",show_alert=True); return
    msg=await c.message.answer("🚀 Подготавливаю сборку…"); await c.answer("Сборка запущена"); schedule(c.from_user.id,up,build_mode,commands,filename,account,msg.chat.id,msg.message_id)
async def begin_build_message(m:Message,upload_id,build_mode,commands,filename):
    up=await db.get_upload(upload_id,m.from_user.id); account=await db.get_account(m.from_user.id)
    if not up or not account: await m.answer("Архив или GitHub не найден."); return
    msg=await m.answer("🚀 Подготавливаю сборку…"); schedule(m.from_user.id,up,build_mode,commands,filename,account,msg.chat.id,msg.message_id)
def schedule(user_id,up,build_mode,commands,filename,account,chat_id,message_id):
    bid=uuid.uuid4().hex[:10]; task=asyncio.create_task(run_build(bid,user_id,up,build_mode,commands,filename,account,chat_id,message_id)); tasks.add(task); task.add_done_callback(tasks.discard)

def project_root(source:Path):
    entries=[p for p in source.iterdir() if p.name not in {".github"}]
    return entries[0] if len(entries)==1 and entries[0].is_dir() else source

async def run_build(bid,user_id,up,build_mode,commands,filename,account,chat_id,message_id):
    await db.create_build(bid,user_id,up.id,build_mode); token=vault.decrypt(account[1]); gh=GitHubClient(token); temp=Path(tempfile.mkdtemp(prefix="build-"+bid+"-")); repo=None
    try:
        source=temp/"source"; extract_zip_safely(Path(up.path),source)
        if build_mode=="auto": plan=detect_build(source)
        elif build_mode=="manual-text": plan=BuildPlan("ручные команды",commands,".")
        else:
            allowed={"build","build.sh","build.gradle","build.gradle.kts","pom.xml"}; safe_name=Path(filename).name
            if safe_name in allowed:
                root=project_root(source); (root/safe_name).write_text(commands,encoding="utf-8"); plan=detect_build(source)
            else: plan=BuildPlan("ручной файл "+safe_name,commands,".")
        await db.update_build(bid,status="detected",detected_type=plan.label)
        wf=source/".github"/"workflows"/"build.yml"; wf.parent.mkdir(parents=True,exist_ok=True); wf.write_text(workflow(plan),encoding="utf-8")
        await bot.edit_message_text("🔍 Режим: <b>"+html.escape(plan.label)+"</b>\n📁 Создаю приватный репозиторий…",chat_id=chat_id,message_id=message_id)
        repo=await gh.create_repo("tg-build-"+bid); await db.update_build(bid,status="uploading",repository=repo); await gh.push(source,repo)
        run_id=await gh.wait_run(repo); await db.update_build(bid,status="building",run_id=run_id)
        link="https://github.com/"+repo+"/actions/runs/"+str(run_id)
        await bot.edit_message_text("🔨 Сборка выполняется…\n<a href=\""+link+"\">GitHub Actions</a>",chat_id=chat_id,message_id=message_id)
        conclusion=await gh.wait_done(repo,run_id)
        if conclusion!="success": raise GitHubError("Workflow завершился: "+conclusion)
        artifact=await gh.artifact(repo,run_id,temp/"artifact.zip"); out=temp/"result"; out.mkdir()
        with zipfile.ZipFile(artifact) as z: z.extractall(out)
        results=[p for p in out.rglob("*") if p.is_file() and p.suffix.lower() in {".jar",".apk"} and "sources" not in p.name.lower() and "javadoc" not in p.name.lower()]
        if not results: raise GitHubError("В артефакте нет .jar или .apk")
        await db.update_build(bid,status="success"); await bot.edit_message_text("✅ Сборка завершена: <b>"+html.escape(plan.label)+"</b>",chat_id=chat_id,message_id=message_id)
        for result in results[:10]:
            if result.stat().st_size<=49*1024*1024: await bot.send_document(chat_id,FSInputFile(result),caption="✅ "+html.escape(result.name))
            else: await bot.send_message(chat_id,"Файл "+html.escape(result.name)+" больше 49 МБ — скачайте из GitHub Actions.")
    except Exception as exc:
        error=str(exc).replace(token,"***")[:1200]; log.exception("Build %s failed",bid); await db.update_build(bid,status="failed",repository=repo,error=error)
        extra=("\n<a href=\"https://github.com/"+repo+"/actions\">Открыть логи</a>") if repo else ""
        try: await bot.edit_message_text("❌ Ошибка:\n<code>"+html.escape(error)+"</code>"+extra,chat_id=chat_id,message_id=message_id)
        except Exception: pass
    finally:
        if settings.delete_repo_after_build and repo:
            try: await gh.delete_repo(repo)
            except Exception: pass
        await gh.close(); shutil.rmtree(temp,ignore_errors=True)

@router.callback_query(F.data=="menu:builds")
async def builds(c:CallbackQuery):
    rows=await db.recent_builds(c.from_user.id); lines=["<b>Последние сборки</b>"]
    for bid,bmode,status,detected,repo,created in rows:
        icon="✅" if status=="success" else "❌" if status=="failed" else "⏳"; link=(" — <a href=\"https://github.com/"+repo+"\">GitHub</a>") if repo else ""; lines.append(f"{icon} <code>{bid}</code> · {html.escape(detected or bmode)} · {status}{link}")
    if len(lines)==1: lines.append("Пока пусто.")
    await c.message.edit_text("\n".join(lines),reply_markup=back()); await c.answer()

async def main():
    global settings,bot,db,vault
    settings=load_settings(); bot=Bot(settings.telegram_token,default=DefaultBotProperties(parse_mode=ParseMode.HTML)); db=Database(settings.database_path); vault=TokenVault(settings.data_dir,settings.fernet_key); await db.init()
    router.message.outer_middleware(AccessMiddleware(settings.allowed_ids)); router.callback_query.outer_middleware(AccessMiddleware(settings.allowed_ids)); dp=Dispatcher(); dp.include_router(router)
    try: await dp.start_polling(bot,allowed_updates=dp.resolve_used_update_types())
    finally: await bot.session.close()
if __name__=="__main__": asyncio.run(main())
