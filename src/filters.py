import pyrogram
import pyrogram.errors
from pyrogram import filters
from pyrogram.types import Message, CallbackQuery
from pyrogram.client import Client
from src.database import db
from src.functions.functions import is_admin as is_admind
from src.utils.logger_config import logger
from pyrogram.enums import ChatMemberStatus


class IsAdmin(filters.Filter):
    def __init__(self):
        self.is_admin = filters.create(self.__is_admin, "is_admin")

    async def __is_admin(
        self, client: Client, message: Message | CallbackQuery
    ) -> bool:
        if isinstance(message, Message):
            return await is_admind(message)
        elif isinstance(message, CallbackQuery):
            callback_query = message
            if callback_query.from_user.id in db.get_admins():
                return True
            try:
                chat_id = callback_query.message.chat.id
                user_id = callback_query.from_user.id
                user = await client.get_chat_member(chat_id, user_id)
                result = bool(
                    user.status
                    in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
                )
                logger.info(f"{user.status}")

                if not result:
                    await callback_query.answer(
                        "Вы не являетесь администратором или основателем!",
                        show_alert=True,
                    )
                    return False
                return True
            except pyrogram.errors.UserNotParticipant:
                return False


is_admin = IsAdmin().is_admin
