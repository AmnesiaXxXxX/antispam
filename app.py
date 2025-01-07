import asyncio
import datetime
import logging
import os
import re
import time
from functools import lru_cache
from logging.handlers import RotatingFileHandler
from typing import List, Optional

import aiohttp
import unidecode
from dotenv import load_dotenv
from pyrogram import Client, filters  # type: ignore
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from users import User, Users

# Загрузка переменных окружения из .env файла
load_dotenv()

# Параметры для логирования
log_dir = "logs"  # Папка для хранения логов
os.makedirs(log_dir, exist_ok=True)  # Создание папки, если она не существует

# Формирование имени файла лога с датой
log_filename = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d.log")
log_path = os.path.join(log_dir, log_filename)

# Настройка логирования
logger = logging.getLogger()
logger.setLevel(logging.INFO)  # Уровень логирования

# Ротация логов (файл размером до 1 МБ, 5 резервных копий)
file_handler = RotatingFileHandler(
    log_path,
    maxBytes=10**6,  # 1 МБ на файл
    backupCount=5,  # Хранение 5 резервных копий
)
file_handler.setLevel(logging.INFO)

# Форматирование логов
formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
file_handler.setFormatter(formatter)

# Добавляем обработчик к логгеру
logger.addHandler(file_handler)

# Токены и ключи для работы с API
token = os.getenv("TOKEN") or exit("TOKEN is not set")
bot_token = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN is not set")
api_id = os.getenv("API_ID") or exit("API_ID is not set")
api_hash = os.getenv("API_HASH") or exit("API_HASH is not set")

# Инициализация бота с использованием токенов
bot = Client(
    "bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
)

# Добавляем после импортов
SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD", "3"))  # Порог по умолчанию


# Функция для проверки пользователя через FunStat API
async def check_user(user_id: int) -> bool | Optional[str]:
    """
    Проверяет, когда пользователь отправил своё первое сообщение.
    Возвращает строку "True"/"False", если прошло более 60 дней с первого сообщения.
    Если возникли ошибки, возвращает сообщение об ошибке.

    :param username: Имя пользователя.
    :return: Строка с результатом проверки.
    """
    if not user_id:
        return False

    try:
        # Выполняем запрос к FunStat API для получения данных пользователя
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://funstat.org/api/v1/users/{user_id}/stats_min",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                result = await response.json()

                first_msg_date_str = result.get("first_msg_date")
                if not first_msg_date_str:
                    return False

                # Преобразуем дату первого сообщения в объект datetime
                first_msg_date = datetime.datetime.strptime(
                    first_msg_date_str, "%Y-%m-%dT%H:%M:%SZ"
                )
                delta = datetime.datetime.now(datetime.UTC) - first_msg_date

                # Если с первого сообщения прошло больше 60 дней, возвращаем True
                if delta >= datetime.timedelta(days=60):
                    return result
                else:
                    return False
    except Exception:
        return False


# Функция для чтения списка запрещенных слов из файла
def get_keywords() -> List[str]:
    """Читает список запрещенных слов из файла."""
    try:
        with open("bad_words.txt", "r", encoding="utf-8") as f:
            keywords = unidecode.unidecode(f.read().lower().replace(" ", "")).split(
                "\n"
            )
        return keywords
    except Exception:
        return []


@bot.on_message(filters.text & filters.command(["add_badword"]))
async def add_badword(client, message: Message):
    word = " ".join(message.text.split(" ")[1:])
    with open("bad_words.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{unidecode.unidecode(word.lower())}")
    keywords = get_keywords()
    await message.reply(
        f"Добавлено слово: {word}\nТекущий список запрещенных слов:\n{', '.join(keywords)}"
    )


@bot.on_message(filters.new_chat_members)
async def on_new_member(client: Client, message: Message):
    # Проверяем, был ли добавлен именно бот
    for new_member in message.new_chat_members:
        if new_member.is_self:
            # Отправляем сообщение, когда бот был добавлен в чат
            await message.reply("Привет! Я был добавлен в этот чат. Чем могу помочь?")
            break


@lru_cache(maxsize=128)
def get_special_patterns() -> List[str]:
    """Возвращает список скомпилированных регулярных выражений для специальных символов."""
    return [
        r"[\u0400-\u04FF]",  # Кириллица
        r"[\u0500-\u052F]",  # Расширенная кириллица
        r"[\u2000-\u206F]",  # Знаки пунктуации
        r"[\u0180-\u024F]",  # Расширенная латиница
        r"[\u1D00-\u1D7F]",  # Фонетические расширения
        r"[\u1E00-\u1EFF]",  # Дополнительная латиница
        r"[\uFE00-\uFE0F]",  # Вариационные селекторы
        r"[\u0300-\u036F]",  # Комбинируемые диакритические знаки
        r"[\u1100-\u11FF]",  # Хангыль
        r"[\u2600-\u26FF]",  # Различные символы
        r"[\u2700-\u27BF]",  # Дополнительные символы
        r"[\uFF00-\uFFEF]",  # Полноширинные формы
    ]


def search_keywords(text: str) -> bool:
    """
    Ищет запрещенные слова и специальные символы в тексте.
    Подсчитывает баллы на основе найденных слов и символов.

    Args:
        text: Анализируемый текст сообщения

    Returns:
        bool: True если количество баллов превышает порог

    Raises:
        ValueError: Если текст пустой или None
    """
    if not text or not isinstance(text, str):
        raise ValueError("Текст должен быть непустой строкой")

    try:
        score = 0
        keywords = get_keywords() or ["слово"]

        # Преобразуем текст и ищем ключевые слова
        normalized_text = unidecode.unidecode(text.lower())
        keyword_pattern = r"\b(" + "|".join(map(re.escape, keywords)) + r")\b"
        found_keywords = len(re.findall(keyword_pattern, normalized_text))

        # Добавляем баллы за найденные ключевые слова
        score += found_keywords

        # Проверяем спец-символы
        special_chars_found = 0
        for pattern in get_special_patterns():
            if re.search(pattern, text):
                special_chars_found += 1

        # Добавляем баллы за спец-символы
        score += special_chars_found * 1.5
        return score >= SPAM_THRESHOLD

    except Exception as e:
        logger.error(f"Ошибка при поиске ключевых слов: {str(e)}")
        return False


@bot.on_message(filters.text & filters.command("set_threshold"))
async def set_threshold(client: Client, message: Message):
    """Команда для изменения порога спама."""
    try:
        # Проверяем права администратора
        chat_member = await client.get_chat_member(
            message.chat.id, message.from_user.id
        )
        if chat_member.status.value not in ["administrator", "owner"]:
            await message.reply("Только администраторы могут менять порог!")
            return

        # Получаем новое значение порога
        new_threshold = float(message.text.split()[1])
        if new_threshold <= 0:
            await message.reply("Порог должен быть положительным числом!")
            return

        # Обновляем значение в памяти
        global SPAM_THRESHOLD
        SPAM_THRESHOLD = new_threshold

        # Читаем текущий .env файл
        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # Обновляем или добавляем SPAM_THRESHOLD
        threshold_line = f"SPAM_THRESHOLD={new_threshold}\n"
        threshold_found = False

        for i, line in enumerate(lines):
            if line.startswith("SPAM_THRESHOLD="):
                lines[i] = threshold_line
                threshold_found = True
                break

        if not threshold_found:
            lines.append(threshold_line)

        # Записываем обновленный .env файл
        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        await message.reply(f"Новый порог установлен и сохранен: {SPAM_THRESHOLD}")

    except (IndexError, ValueError):
        await message.reply("Использование: /set_threshold [число]")
    except Exception as e:
        logger.error(f"Ошибка при установке порога: {str(e)}")
        await message.reply(f"Ошибка при установке порога: {str(e)}")


# Команда /start
@bot.on_message(filters.text & filters.command(["start"]))
async def start(client: Client, message: Message):
    await message.reply(
        "Добро пожаловать! Я антиспам бот. Используйте /list, чтобы увидеть текущий список запрещенных слов."
    )


@bot.on_message(filters.text & filters.command(["gen_regex"]))
async def gen_regex(client: Client, message: Message):
    keywords = get_keywords() or ["слово"]
    # Составляем регулярное выражение для поиска запрещенных слов
    pattern = r"(" + "|".join(keywords) + r")"
    await message.reply(pattern)


@bot.on_message(filters.text & filters.command(["invert"]))
async def invert(client: Client, message: Message):
    await message.reply(unidecode.unidecode(message.text.split("#")[1]))


# Команда /list - выводит список запрещенных слов
@bot.on_message(filters.text & filters.command(["list"]))
async def list_command(client: Client, message: Message) -> None:
    """Команда для вывода списка запрещенных слов."""
    try:
        bad_words = get_keywords()
        await message.reply(f"```Запретки\n{"\n".join(bad_words)}```")
    except Exception:
        await message.reply("Ошибка при обработке запроса.")


# Команда /check - проверяет пользователя через FunStat API
@bot.on_message(filters.text & filters.command(["check"]))
async def check_command(client: Client, message: Message) -> None:
    """Команда для проверки пользователя через FunStat API."""
    try:
        user_id = message.text.split(" ")[1]
        if not user_id.isdigit():
            user = await client.get_chat_member(message.chat.id, user_id)
            user_id = int(user.user.id)
        else:
            user_id = int(user_id)
        result = (
            await check_user(user_id) or "Пользователь не найден."
        )  # Проверяем пользователя через API
        await message.reply(result)
    except IndexError:
        await message.reply("Укажите имя пользователя после команды.")
    except Exception as e:
        await message.reply(f"Ошибка при обработке запроса. {e}")


# Отмена действия по кнопке "cancel"
@bot.on_callback_query(filters.regex(r"delete"))
async def delete(client: Client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    chat_member = await client.get_chat_member(chat_id, callback_query.from_user.id)
    if chat_member.status.value not in ["administrator", "owner"]:
        await callback_query.answer(
            "Вы не являетесь администратором или основателем!", show_alert=True
        )
    if (
        not chat_member.privileges.can_delete_messages
        and not chat_member.privileges.can_restrict_members
    ):
        await callback_query.answer(
            "У вас нет прав для выполнения этого действия!", show_alert=True
        )
        return
    await client.delete_messages(
        callback_query.message.chat.id, callback_query.message.reply_to_message.id
    )
    await callback_query.message.delete()


@bot.on_callback_query(filters.regex(r"cancel"))
async def cancel(client: Client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    chat_member = await client.get_chat_member(chat_id, callback_query.from_user.id)
    if chat_member.status.value in ["administrator", "owner"]:
        await callback_query.message.delete()
    else:
        await callback_query.answer(
            "Вы не являетесь администратором или основателем!", show_alert=True
        )


# Бан пользователя по кнопке
@bot.on_callback_query(filters.regex(r"ban_user_(\d+)_(\d+)"))
async def check_admin_or_moderator(client: Client, callback_query: CallbackQuery):
    try:
        callback_query.data = callback_query.data.replace("ban_user_", "")
        msg_id = int(callback_query.data.split("_")[1])
        user_id = int(callback_query.data.split("_")[0])
        chat_id = callback_query.message.chat.id
        chat_member = await client.get_chat_member(chat_id, callback_query.from_user.id)
        target = await client.get_chat_member(chat_id, user_id)
        # Проверяем, является ли пользователь администратором
        if chat_member.status.value not in ["administrator", "owner"]:
            await callback_query.answer(
                "Вы не являетесь администратором или основателем!", show_alert=True
            )
            return
        if (
            not chat_member.privileges.can_delete_messages
            and not chat_member.privileges.can_restrict_members
        ):
            await callback_query.answer(
                "У вас нет прав для выполнения этого действия!", show_alert=True
            )
            return

        # Баним пользователя, если его ID не равен исключенному
        if user_id != 5957115070:
            if target.status.value in ["administrator", "owner"]:
                await callback_query.answer(
                    "Цель является администратором, не могу забанить(", show_alert=True
                )
                return
            else:
                await client.ban_chat_member(chat_id, user_id)
        else:
            await callback_query.answer(
                "Ты уверен что себя хочешь забанить?", show_alert=True
            )
            return

        await callback_query.answer("Забанен!", show_alert=True)
        await client.delete_messages(chat_id, [msg_id, callback_query.message.id])

        with open("ban_sentenses.txt", "a", encoding="utf-8") as f:
            f.write(callback_query.message.reply_to_message.text + "\n")
    except Exception as e:
        await callback_query.answer(f"Ошибка при бане: {e}", show_alert=True)


# Функция для создания кнопок с баном и отменой
def ban_button(user_id: int, msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="Забанить",
                    callback_data=f"ban_user_{user_id}_{msg_id}",
                ),
                InlineKeyboardButton(
                    text="Просто удалить",
                    callback_data="delete",
                ),
                InlineKeyboardButton(
                    text="Галя, отмена",
                    callback_data="cancel",
                ),
            ]
        ]
    )


@bot.on_message(filters.text & filters.command(["get_autos"]))
async def get_autos(client: Client, message: Message):
    autos = open("autos.txt", "r", encoding="utf-8").read().split("\n")
    await message.reply("\n".join(autos))


@bot.on_message(filters.text & filters.command(["autoclean"]))
async def add_autos(client: Client, message: Message):
    if message.from_user.status.value not in ["administrator", "owner"]:
        await message.reply("Вы не являетесь администратором или основателем!")
        return

    autos = open("autos.txt", "r", encoding="utf-8").read().split("\n")
    if message.chat.id not in autos:
        autos.append(str(message.chat.id))
    else:
        await message.reply("Чат уже есть!")
    with open("autos.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(autos))
    msg = await message.reply("Чат добавлен!")
    await asyncio.sleep(15)
    await message.delete()
    await msg.delete()


@bot.on_message(filters.text & filters.command(["remove_autoclean"]))
async def remove_autos(client: Client, message: Message):
    autos = open("autos.txt", "r", encoding="utf-8").read().split("\n")
    autos.remove(str(message.chat.id))
    with open("autos.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(autos))
    await message.reply("Авто удалено!")


# Основная логика для обработки текстовых сообщений
@bot.on_message(filters.text & ~filters.channel)
async def main(client: Client, message: Message) -> None:
    """
    Обрабатывает входящие текстовые сообщения, проверяет наличие запрещенных слов.
    Если слова найдены, удаляет сообщение и логирует.
    """
    try:
        autos = open("autos.txt", "r", encoding="utf-8").read().split("\n")

        if not message.text:
            return  # Если сообщение пустое, игнорируем его

        # Преобразуем текст в нормализованный вид
        text = message.text

        # Проверяем наличие запрещенных слов
        if search_keywords(text):
            # Проверяем, является ли пользователь валидным
            is_user_valid = await check_user(message.from_user.id)

            # Если пользователь не прошел проверку или является исключением, пропускаем его
            if is_user_valid == "False" and message.from_user.id != 5957115070:
                return
            else:
                await message.forward("amnesiawho1")  # Пересылаем сообщение в канал
            if str(message.chat.id) in autos:
                await message.reply(
                    "Подозрительное сообщение!",
                    reply_markup=ban_button(message.from_user.id, message.id),
                )
                return
            await message.delete()
    except Exception as e:
        logger.exception(f"Error processing message: {e}")


# Запуск бота
if __name__ == "__main__":
    start_time = time.time()  # Засекаем время старта бота
    bot.run()  # Запускаем бота

    # Логируем время работы бота
    total_time = round(time.time() - start_time, 2)
    logger.info(
        f"Total uptime {total_time if total_time < 3600 else int(total_time/60)} seconds. Bot stopped."
    )
