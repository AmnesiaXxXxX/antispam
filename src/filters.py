import pyrogram
import pyrogram.errors
from pyrogram import filters
from pyrogram.types import Message

from src.database import db
from src.setup_bot import bot


class IsAdmin(filters.Filter):
    def __init__(self):
        self.is_admin = filters.create(self.__is_admin, "is_admin")
        
    
    async def __is_admin(self, __, message: Message) -> bool:
        if message.from_user.id in db.get_admins():
            return True
        try:
            user = await bot.get_chat_member(message.chat.id, message.from_user.id)
            return bool(user.status in ["creator", "administrator"])
        except pyrogram.errors.UserNotParticipant:
            return False



is_admin = IsAdmin()


