import logging
import os
import re
import random
import datetime
from typing import List, Optional
from pyrogram import Client, filters #type: ignore
from pyrogram.types import Message
import unidecode
import aiohttp
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler

# Загрузка переменных окружения
load_dotenv()

# Параметры для логирования
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# Имена файлов логов с ротацией
log_filename = datetime.datetime.utcnow().strftime("%Y-%m-%d-%H.log")
log_path = os.path.join(log_dir, log_filename)

# Настройка логирования
logger = logging.getLogger()
logger.setLevel(logging.INFO)
logging.getLogger("pyrogram").setLevel(logging.CRITICAL)
logging.getLogger("pyrogram.client").setLevel(logging.CRITICAL)
logging.getLogger("pyrogram.session").setLevel(logging.CRITICAL)
logging.getLogger("pyrogram.connection").setLevel(logging.CRITICAL)
logging.getLogger("pyrogram.network").setLevel(logging.CRITICAL)

# Используем ротацию логов
file_handler = RotatingFileHandler(
    log_path, maxBytes=10**6, backupCount=5
)  # 1MB на файл, 5 резервных
file_handler.setLevel(logging.INFO)
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

# Токены
token = os.getenv("TOKEN") or exit("TOKEN is not set")
bot_token = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN is not set")

# Инициализация бота
bot = Client(
    "bot",
    api_id=20853958,
    api_hash="3884c622761024ef3afeb01082ad00c7",
    bot_token=bot_token,
)


async def check_user(username: Optional[str]) -> str:
    """
    Проверяет, когда пользователь отправил своё первое сообщение.
    Возвращает строку "True"/"False", если прошло более 60 дней с первого сообщения.
    Если возникли ошибки, возвращает сообщение об ошибке.

    :param username: Имя пользователя.
    :return: Строка с результатом проверки.
    """
    if not username:
        logger.info("Username is None.")
        return "Пользователь не найден"

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://funstat.org/api/v1/users/{username}/stats_min",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                result = await response.json()

                if not result.get("success"):
                    logger.warning(f"User {username} not found in API.")
                    return "Пользователь не найден"

                first_msg_date_str = result.get("first_msg_date")
                if not first_msg_date_str:
                    logger.error(f"Missing expected fields for {username}.")
                    return "API не вернул ожидаемые поля"

                first_msg_date = datetime.datetime.strptime(
                    first_msg_date_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                delta = datetime.datetime.utcnow() - first_msg_date

                if delta >= datetime.timedelta(days=60):
                    logger.info(f"User {username} passed 60 days check.")
                    return "True"
                else:
                    logger.info(f"User {username} did not pass 60 days check.")
                    return "False"
    except Exception as e:
        logger.exception(f"Error while checking user {username}: {e}")
        return "Ошибка при обработке запроса"


def get_keywords() -> List[str]:
    """Читает список запрещенных слов из файла."""
    try:
        with open("bad_words.txt", "r", encoding="utf-8") as f:
            keywords = unidecode.unidecode(f.read().lower().strip()).split("\n")
        logger.info(f"Loaded {len(keywords)} bad words.")
        return keywords
    except Exception:
        logger.exception("Error reading bad_words.txt")
        return []


def search_keywords(text: str) -> List[str]:
    """
    Ищет запрещенные слова в тексте и возвращает список найденных слов.

    :param text: Текст сообщения.
    :return: Список найденных запрещенных слов.
    """
    try:
        keywords = get_keywords() or ["слово"]
        pattern = (
            r"\b(" + "|".join([re.escape(keyword) for keyword in keywords]) + r")\b"
        )
        found_keywords = [
            match.group() for match in re.finditer(pattern, text, re.IGNORECASE)
        ]
        if found_keywords:
            logger.info(f"Found bad words: {found_keywords}")
        return found_keywords
    except Exception:
        logger.exception(f"Error searching keywords in text: {text}")
        return []

@bot.on_message(filters.text & filters.command(["start"]))
async def start(client: Client, message:Message):
    await message.reply("Добро пожаловать! Я антиспам бот. Используйте /list, чтобы увидеть текущий список запрещенных слов.")

@bot.on_message(filters.text & filters.command(["list"]))
async def list_command(client: Client, message: Message) -> None:
    """Команда для вывода списка запрещенных слов."""
    try:
        bad_words = get_keywords()
        await message.reply(", ".join(bad_words))
        logger.error(f"Sent list of bad words to {message.from_user.username}.")
    except Exception as e:
        logger.exception(f"Error processing list command: {e}")


@bot.on_message(filters.text & filters.command(["check"]))
async def check_command(client: Client, message: Message) -> None:
    """Команда для проверки пользователя через FunStat API."""
    try:
        username = message.text.split(" ")[1]
        result = await check_user(username)
        await message.reply(result)
        logger.info(f"Processed check command for user {username}. Result: {result}")
    except IndexError:
        await message.reply("Укажите имя пользователя после команды.")
        logger.warning(
            f"User {message.from_user.username} missed username for check command."
        )
    except Exception as e:
        logger.exception(f"Error processing check command: {e}")
        await message.reply("Ошибка при обработке запроса.")


@bot.on_message(filters.text)
async def main(client: Client, message: Message) -> None:
    """
    Обрабатывает входящие текстовые сообщения, проверяет наличие запрещенных слов.
    Если слова найдены, удаляет сообщение и логирует.

    :param client: Экземпляр бота.
    :param message: Сообщение пользователя.
    """
    try:
        if message is None or not message.text:
            logger.info("Empty message received.")
            return

        username = message.from_user.username if message.from_user else None
        is_user_valid = await check_user(username)

        if is_user_valid == "False":
            logger.info(f"User {username} is not valid, skipping message.")
            return

        text = unidecode.unidecode(message.text)
        bad_words = search_keywords(text)

        if bad_words:
            await message.delete()
            logger.info(
                f"Deleted message from {message.from_user.username} due to bad words: {bad_words}"
            )
        elif random.randint(0, 100) < 25:
            await message.reply(
                "Если вы администратор канала и считаете, что удалённое сообщение не было спамом, "
                "пожалуйста, напишите @amnesiawho1, исправим!"
            )
            logger.info(
                f"Sent reply to {message.from_user.username} regarding deleted message."
            )
    except Exception as e:
        logger.exception(
            f"Error processing message from {message.from_user.username if message.from_user else 'unknown'}: {e}"
        )

if __name__ == "__main__":
    try:
        bot.run()
    except Exception as e:
        logger.exception(f"Error running bot: {e}")
        logger.exception(f"Bot stopped at {datetime.datetime.now()}")
    finally:
        logger.info(f"Bot started at {datetime.datetime.now()}")