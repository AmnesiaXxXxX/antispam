import pyrogram
import pyrogram.errors
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.client import Client
from src.database import db
from src.setup_bot import bot


class IsAdmin(filters.Filter):
    def __init__(self):
        self.is_admin = filters.create(self.__is_admin, "is_admin")
    
    
    async def __is_admin(self, client: Client, message: Message | CallbackQuery) -> bool:
        if isinstance(message, Message):
            if message.from_user.id in db.get_admins():
                return True
            try:
                user = await bot.get_chat_member(message.chat.id, message.from_user.id)
                result = bool(user.status in ["creator", "administrator"])
                if not result:
                    await message.reply("Вы не являетесь администратором или основателем!")
                    return False
                return True
            except pyrogram.errors.UserNotParticipant:
                return False
        elif isinstance(message, CallbackQuery):
            try:
                callback_query = message
                chat_id = callback_query.message.chat.id
                chat_member = await client.get_chat_member(chat_id, callback_query.from_user.id)
                if chat_member.status.value not in ["administrator", "creator"]:
                    await callback_query.answer(
                        "Вы не являетесь администратором или основателем!", show_alert=True
                    )
                    return False
                return True
            except pyrogram.errors.UserNotParticipant:
                return False
is_admin = IsAdmin()


