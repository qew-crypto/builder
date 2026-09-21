import shutil, stat, zipfile
from pathlib import Path, PurePosixPath
class UnsafeArchive(ValueError): pass

def extract_zip_safely(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True); total=0; files=[]
    with zipfile.ZipFile(archive) as zf:
        infos=zf.infolist()
        if len(infos)>3000: raise UnsafeArchive("В архиве больше 3000 файлов")
        for info in infos:
            p=PurePosixPath(info.filename.replace("\\","/"))
            if p.is_absolute() or ".." in p.parts: raise UnsafeArchive("Опасный путь в ZIP")
            if not p.parts or p.parts[0] in {".git","__MACOSX"}: continue
            if len(p.parts)>=2 and p.parts[0]==".github" and p.parts[1]=="workflows": continue
            if stat.S_ISLNK(info.external_attr>>16): raise UnsafeArchive("Символические ссылки запрещены")
            if info.is_dir(): continue
            total += info.file_size
            if info.file_size>50*1024*1024 or total>150*1024*1024: raise UnsafeArchive("Архив слишком большой после распаковки")
            out=destination.joinpath(*p.parts); out.parent.mkdir(parents=True,exist_ok=True)
            with zf.open(info) as src,out.open("wb") as dst: shutil.copyfileobj(src,dst)
            files.append(out)
    if not files: raise UnsafeArchive("Архив пуст")
    return files
