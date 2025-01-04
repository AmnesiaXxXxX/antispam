# Стандартные библиотеки
import os
import datetime
import time

# Сторонние библиотеки
from dotenv import load_dotenv
from pyrogram import Client

# Локальные импорты
from users import Users
from _src.handlers.commands import register_commands
from _src.handlers.callbacks import register_callbacks
from _src.utils.logger import setup_logger
from _src.utils.handlers import setup_message_handlers

# Настройка логгера
logger = setup_logger()

# Загрузка конфигурации
try:
    if os.path.exists('.env'):
        load_dotenv()
        logger.info("Env vars loaded from .env")
    else:
        logger.warning("No .env file found")
except Exception as e:
    logger.error(f"Error loading env vars: {e}")

# Проверка необходимых переменных окружения
required_vars = {
    "TOKEN": os.getenv("TOKEN"),
    "BOT_TOKEN": os.getenv("BOT_TOKEN"),
    "API_ID": os.getenv("API_ID"),
    "API_HASH": os.getenv("API_HASH")
}

for var_name, value in required_vars.items():
    if not value:
        exit(f"{var_name} is not set")

# Инициализация бота
bot = Client(
    "bot",
    api_id=required_vars["API_ID"],
    api_hash=required_vars["API_HASH"],
    bot_token=required_vars["BOT_TOKEN"]
)

# Инициализация базы данных
users_db = Users()

# Регистрация обработчиков
register_commands(bot)
register_callbacks(bot)
setup_message_handlers(bot, users_db)

if __name__ == "__main__":
    start_time = time.time()
    try:
        logger.info("Starting bot...")
        bot.run()
    finally:
        uptime = datetime.timedelta(seconds=int(time.time() - start_time))
        logger.info(f"Bot stopped. Uptime: {uptime}")
