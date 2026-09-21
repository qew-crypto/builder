from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message


class AccessMiddleware(BaseMiddleware):
    def __init__(self, allowed_ids: frozenset[int]):
        self.allowed_ids = allowed_ids

    async def __call__(self, handler, event, data):
        user = getattr(event, "from_user", None)
        if user and user.id in self.allowed_ids:
            return await handler(event, data)
        if isinstance(event, CallbackQuery):
            await event.answer("Доступ запрещён", show_alert=True)
        elif isinstance(event, Message):
            await event.answer("⛔ У вас нет доступа к этому боту.")
