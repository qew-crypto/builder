from aiogram.types import InlineKeyboardButton as B, InlineKeyboardMarkup as M

def main_menu(connected):
    rows=[]
    if connected:
        rows += [[B(text="📦 Загрузить ZIP",callback_data="menu:upload")],[B(text="🧱 Сборки",callback_data="menu:builds")],[B(text="🔌 Отключить GitHub",callback_data="menu:disconnect")]]
    else: rows.append([B(text="🔐 Подключить GitHub",callback_data="menu:connect")])
    rows.append([B(text="ℹ️ Помощь",callback_data="menu:help")]); return M(inline_keyboard=rows)
def mode(upload_id): return M(inline_keyboard=[[B(text="⚡ Автоматически",callback_data=f"auto:{upload_id}")],[B(text="🛠 Вручную",callback_data=f"manual:{upload_id}")],[B(text="⬅️ Меню",callback_data="menu:home")]])
def manual(upload_id): return M(inline_keyboard=[[B(text="📝 Вставить команды",callback_data=f"manualtext:{upload_id}")],[B(text="📄 Отправить build-файл",callback_data=f"manualfile:{upload_id}")],[B(text="⬅️ Назад",callback_data=f"choose:{upload_id}")]])
def back(): return M(inline_keyboard=[[B(text="⬅️ Меню",callback_data="menu:home")]])
