# region IMPORTS
import inspect
import logging
import os
import re
import datetime
import asyncio
import time
from typing import List, Optional
import pyrogram
from pyrogram import Client, filters  # type: ignore
from pyrogram.types import (
    Message,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    CallbackQuery,
)

import unidecode
import aiohttp
from dotenv import load_dotenv
from logging.handlers import RotatingFileHandler
from users import Users, User
# endregion


# region ENVIRONMENT_SETUP
# Загрузка переменных окружения из .env файла
load_dotenv()

# Токены и ключи для работы с API
token = os.getenv("TOKEN") or exit("TOKEN is not set")
bot_token = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN is not set")
api_id = os.getenv("API_ID") or exit("API_ID is not set")
api_hash = os.getenv("API_HASH") or exit("API_HASH is not set")
# endregion


# region LOGGING_SETUP
# Папка для хранения логов
log_dir = "logs"
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
# endregion


# region BOT_INITIALIZATION
# Инициализация бота с использованием токенов
bot = Client(
    "bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
)
# endregion


# region 1.FUNCTIONS
#
#
#
#
#


# region BAN_FUNCTION


async def ban_user(
    client: Client,
    user_id: int,
    channels: List[str] = open("channels.txt", "r", encoding="utf-8")
    .read()
    .splitlines(),
):
    try:
        for channel in channels:
            try:
                await client.ban_chat_member(channel, user_id)
                logging.info(f"Ban user {user_id} in channel {channel}")
                await asyncio.sleep(0.5)
            except Exception:
                logging.warning(f"Failed to ban user {user_id} in channel {channel}")
                pass
        with open("banned.txt", "a", encoding="utf-8") as f:
            f.write(f"{user_id}\n")

    except Exception as e:
        logger.exception(
            f"Error at {ban_user.__name__}:{inspect.getframeinfo(inspect.currentframe()).lineno}: {e}"
        )
        return False


# endregion


# region CHECK_USER
async def check_user(user_id: int) -> bool | Optional[str]:
    """
    Проверяет, когда пользователь отправил своё первое сообщение.
    Возвращает строку "True"/"False", если прошло более 60 дней с первого сообщения.
    Если возникли ошибки, возвращает сообщение об ошибке.

    :param user_id: ID пользователя.
    :return: Строка с результатом проверки.
    """
    if not user_id:
        logger.exception(
            f"Error at {check_user.__name__}:{inspect.getframeinfo(inspect.currentframe()).lineno}: User ID is required"
        )
        raise ValueError("User ID is required")
    # if user_id == 5957115070:
    #     return False
    try:
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

                # Преобразуем дату первого сообщения в объект datetime с временной зоной UTC
                first_msg_date = datetime.datetime.strptime(
                    first_msg_date_str, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.timezone.utc)
                delta = datetime.datetime.now(datetime.timezone.utc) - first_msg_date
                logging.info(delta)
                # Если с первого сообщения прошло больше 60 дней, возвращаем True
                if delta >= datetime.timedelta(days=60):
                    return result
                else:
                    return False
    except Exception as e:
        logging.error(f"Error fetching data: {e}")
        return False


# endregion


# region GET_KEYWORDS
def get_keywords() -> List[str]:
    """
    Читает список запрещенных слов из файла.
    """
    try:
        with open("bad_words.txt", "r", encoding="utf-8") as f:
            keywords = unidecode.unidecode(
                f.read().lower().replace(" ", "")
            ).splitlines()
        return keywords
    except Exception:
        return []


# endregion


# region ADD_BADWORD
@bot.on_message(filters.command(["add_badword"]))
async def add_badword(client, message: Message):
    word = " ".join(message.text.split(" ")[1:])
    with open("bad_words.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{unidecode.unidecode(word.lower())}")
    keywords = get_keywords()
    await message.reply(
        f"Добавлено слово: {word}\nТекущий список запрещенных слов:\n{', '.join(keywords)}"
    )


# endregion


# region ON_NEW_MEMBER
@bot.on_message(filters.new_chat_members)
async def on_new_member(client: Client, message: Message):
    for new_member in message.new_chat_members:
        if new_member.is_self:
            add_new_chat(message.chat.id)
            await start(client, message)


# endregion


# region SEARCH_KEYWORDS    
def search_keywords(text: str) -> bool:
    """
    Ищет запрещенные слова в тексте и возвращает True, если их больше 3.

    :param text: Текст сообщения.
    :return: True, если найдено больше 3 запрещенных слов.
    """

    text = unidecode.unidecode(text)

    try:
        keywords = get_keywords() or ["слово"]
        pattern = r"(" + "|".join(keywords) + r")"

        found_keywords = [
            match.group() for match in re.finditer(pattern, text, re.IGNORECASE)
        ]
        return len(found_keywords) > 4
    except Exception:
        return False


# endregion


# region BAN
@bot.on_message(filters.command(["ban"]) & filters.user(5957115070))
async def ban(client: Client, message: Message):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    elif message.text.split(" ")[1:]:
        user_id = int(message.text.split(" ")[1])
    else:
        await message.reply("Укажите ID пользователя после команды.")
        return
    if not user_id:
        return
    await ban_user(client, user_id)

    await message.reply(f"Пользователь `{user_id}` забанен.")


# endregion


# region IGNORE
@bot.on_message(filters.command(["ignore"]))
async def ignore(client: Client, message: Message):
    if message.reply_to_message:
        if message.reply_to_message:
            user_id = message.reply_to_message.from_user.id
    elif message.text.split(" ")[1:]:
        user_id = int(message.text.split(" ")[1])
    else:
        await message.reply("Укажите ID пользователя после команды.")
        return
    if not user_id:
        return

    ignore_list = open("ignore.txt", "r", encoding="utf-8").read().splitlines()
    if user_id not in ignore_list:
        with open("ignore.txt", "a", encoding="utf-8") as f:
            f.write(f"\n{user_id}")
        await message.reply(f"Пользователь `{user_id}` добавлен в список игнорируемых.")
    else:
        await message.reply(f"Пользователь `{user_id}` уже в списке игнорируемых.")


# endregion


# region START_COMMAND
@bot.on_message(filters.command(["start"]))
async def start(client: Client, message: Message):
    await message.reply(
        """
<b>👋 Всем привет!</b> Я <b>антиспам-бот</b>. 🛡️
        
📝 <b>Контакты</b> 
Хотите написать оскорбления админу, используйте команду <b>/contact</b>. 📬

💡 <b>Есть идеи для улучшения?</b> 
Одмены, не стесняйтесь писать через тот же <b>/contact</b>. Мы ждём ваши предложения! ✨

ℹ️ <b>Интересно, как я работаю?</b> 
Воспользуйтесь командой <b>/info</b> для подробностей. 🔍
        """
    )


# endregion


# region INFO_COMMAND
@bot.on_message(filters.command(["info"]))
async def info(client: Client, message: Message):
    """
    Информация о механизме фильтрации бота.
    """
    await message.reply(
        """
<b>ℹ️ Информация о боте</b>

<b>🛠️ Механизм фильтрации:</b>
🔹 <i>Фильтрация сообщений:</i> Все входящие сообщения проверяются на наличие запрещенных слов из заранее заданного списка, который можно редактировать через команды.  
🔹 <i>Обработка нарушений:</i>  
    - Если в сообщении обнаружено <b>более 3 запрещенных слов</b>, оно автоматически удаляется.  
    - Нарушения фиксируются, и сообщения могут быть переданы администратору для принятия мер.  
🔹 <i>Анализ активности пользователей:</i>  
    - Проверка через <b>API FunStat</b>:  
        * Если пользователь не отправлял сообщений более <b>60 дней</b>, он помечается как подозрительный.  
🔹 <i>Удобные кнопки для администраторов:</i>  
    - <b>Заблокировать пользователя</b>.  
    - <b>Удалить сообщение</b>.  
    - <b>Отменить действие</b>.  

<b>✨ Ключевые особенности:</b>
✔️ Автоматическое удаление сообщений с запрещенными словами.  
✔️ Прямое взаимодействие с администраторами чата для мониторинга активности.  
✔️ Возможность настройки автоматической очистки чатов от подозрительных сообщений.  

<b>💡 Дополнительная информация:</b>
Фильтрация происходит <b>в реальном времени</b>, не требуя дополнительных действий от пользователей. Администраторы могут управлять списком запрещенных слов и настраивать автоматическое поведение через команды.

<b>🔗 Рекомендация:</b>  
Если вам нужен сервис для пробива или поиска информации о людях или каналах в Telegram, попробуйте бот <b>FunStat</b>.  
🌟 Ссылка: <a href="https://t.me/ofunstat_robot?start=0101BE5C126301000000">FunStat</a>  

💬 Для связи с администратором используйте команду: /contact
        """
    )


# endregion


# region CONTACT_COMMAND
@bot.on_message(filters.command(["contact"]) & filters.private)
async def contact(client: Client, message: Message):
    await client.send_message(
        "amnesiawho1",
        f"Новая попытка связаться от {message.from_user.username or message.chat.id}",
    )
    await message.reply("@amnesiawho1")


# endregion


# region GEN_REGEX_COMMAND
@bot.on_message(filters.command(["gen_regex"]))
async def gen_regex(client: Client, message: Message):
    keywords = get_keywords() or ["слово"]
    # Составляем регулярное выражение для поиска запрещенных слов
    pattern = r"(" + "|".join(keywords) + r")"
    await message.reply(pattern)


# endregion


# region INVERT_COMMAND
@bot.on_message(filters.command(["invert"]))
async def invert(client: Client, message: Message):
    """
    Inverts the given text.

    Example: /invert#hello -> hello
    """
    text = message.text.split(" ", 1)[1]
    if not text:
        await message.reply("Empty message")
    await message.reply(f"`{unidecode.unidecode(text)}`")


# endregion


# region LIST_COMMAND
@bot.on_message(filters.command(["list"]))
async def list_command(client: Client, message: Message) -> None:
    """Команда для вывода списка запрещенных слов."""
    try:
        bad_words = get_keywords()
        await message.reply(f"```Запретки\n{'\n'.join(bad_words)}```")
    except Exception:
        await message.reply("Ошибка при обработке запроса.")


# endregion


# region CHECK_COMMAND
@bot.on_message(filters.text & filters.command(["check"]))
async def check_command(client: Client, message: Message) -> None:
    """Команда для проверки пользователя через FunStat API."""
    try:
        user_id = message.text.split(" ")[1]
        if not user_id.isdigit():
            user = await client.get_chat_member(message.chat.id, user_id)
            user_id = user.user.id
        else:
            user_id = int(user_id)
        result = str(await check_user(user_id))  # Проверяем пользователя через API
        await message.reply(result or "Пользователь не найден.")
    except IndexError:
        await message.reply("Укажите имя пользователя после команды.")
    except Exception as e:
        await message.reply(f"Ошибка при обработке запроса. {e}")


# endregion


# region DELETE_CALLBACK
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


# endregion


# region CANCEL_CALLBACK
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


# endregion


# region BAN_CALLBACK
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


# endregion


# region BAN_BUTTON
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


# endregion


# region GET_AUTOS
@bot.on_message(filters.text & filters.command(["get_autos"]))
async def get_autos(client: Client, message: Message):
    autos = open("autos.txt", "r", encoding="utf-8").read().split("\n")
    await message.reply("\n".join(autos))


# endregion


# region AUTOCLEAN_COMMANDS
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


# endregion


# region ADD_NEW_CHAT
def add_new_chat(chat_id: int) -> None:
    with open("channels.txt", "r", encoding="utf-8") as r:
        channels = r.read().splitlines()

    channel_id = str(chat_id)
    if channel_id not in channels:
        with open("channels.txt", "a", encoding="utf-8") as w:
            if channel_id.startswith("-"):
                w.write(f"{channel_id}\n")


# endregion


# endregion  # FUNCTIONS


# region MAIN_HANDLER
@bot.on_message(filters.text & ~filters.channel & ~filters.private)
async def main(client: Client, message: Message) -> None:
    """
    Обрабатывает входящие текстовые сообщения, проверяет наличие запрещенных слов.
    Если слова найдены, удаляет сообщение и логирует.
    """

    ignore_list = open("ignore.txt", "r", encoding="utf-8").read().splitlines()
    if message.from_user.id in ignore_list:
        return
    logging.info(
        f"{message.from_user.id} to {f'https://t.me/{message.chat.username}' or message.chat.id }: {" ".join(message.text.splitlines())}"
    )
    try:
        add_new_chat(message.chat.id)

        if search_keywords(message.text):
            if not await check_user(message.from_user.id):
                await message.forward("amnesiawho1")
                await message.delete()
                await ban_user(client, message.from_user.id)
            # else:
            #     with open("ignore.txt", "a", encoding="utf-8") as f:
            #         f.write(f"\n{message.from_user.id}")

    except Exception as e:
        logger.exception(f"Error processing message: {e}")


# endregion


# region BOT_RUNNER
if __name__ == "__main__":
    start_time = time.time()  # Засекаем время старта бота
    bot.run()  # Запускаем бота

    # Логируем время работы бота
    total_time = round(time.time() - start_time, 2)
    logger.info(
        f"Total uptime {total_time if total_time < 3600 else int(total_time/60)} seconds. Bot stopped."
    )
# endregion
