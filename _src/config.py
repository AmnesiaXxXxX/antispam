import os
import logging
from dotenv import load_dotenv

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Загрузка переменных окружения
try:
    if os.path.exists('.env'):
        load_dotenv()
        logger.info("Environment variables loaded from .env file")
    else:
        logger.warning(".env file not found. Using system environment variables")
except Exception as e:
    logger.error(f"Error loading environment variables: {e}")

# API Credentials
TOKEN = os.getenv("TOKEN") or exit("TOKEN is not set")
BOT_TOKEN = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN is not set") 
API_ID = os.getenv("API_ID") or exit("API_ID is not set")
API_HASH = os.getenv("API_HASH") or exit("API_HASH is not set")
