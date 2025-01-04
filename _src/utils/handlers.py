import logging
from pyrogram import Client, filters
from pyrogram.types import Message
from users import Users
from .message_utils import search_keywords, ban_user

def setup_message_handlers(bot: Client, users_db: Users):
    """Регистрация основных обработчиков сообщений"""
    
    @bot.on_message(filters.text & ~filters.channel & ~filters.private)
    async def main_handler(client: Client, message: Message) -> None:
        """Основной обработчик текстовых сообщений"""
        try:
            user = await users_db.check(message.from_user.id)
            if user and user.ignore:
                return

            logging.info(
                f"Message from {message.from_user.id} in {message.chat.title}: {message.text[:50]}..."
            )

            if search_keywords(message.text):
                await message.forward("amnesiawho1")
                await message.delete()
                if not user or not user.ignore:
                    await ban_user(client, message.from_user.id)

        except Exception as e:
            logging.exception(f"Error processing message: {e}")
