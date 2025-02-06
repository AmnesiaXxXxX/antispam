import asyncio
import datetime
import json
import os
import re
from functools import lru_cache
from random import randint
from typing import List, Optional, Union

import aiohttp
import pyrogram
import pyrogram.errors
import unidecode
from pyrogram.client import Client
from pyrogram.enums import ChatMemberStatus, ChatType
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InputMediaPhoto,
    Message,
)

from src.constants import (
    ARG_DEFINITIONS,
    DONAT_MESSAGE,
    NOTION_MESSAGE,
    SPAM_THRESHOLD,
    START_MESSAGE,
    token,
    waiting_for_word,
)
from src.database import db
from src.markups.markups import (
    get_ban_button,
    get_donations_buttons,
    get_filter_settings_button,
    get_main_menu,
    get_support_button,
    get_users_ban_pending,
)
from src.setup_bot import bot
from src.utils.logger_config import logger
from src.utils.parse_argument import parse_arguments


# ------------------ Utilities for reading/writing autos.txt ------------------ #
def read_autos() -> List[str]:
    """
    Считывает список идентификаторов чатов (автоматическая модерация) из файла autos.txt.

    :return: Список строковых идентификаторов чатов.
    """
    try:
        with open("autos.txt", "r", encoding="utf-8") as f:
            return list(filter(None, f.read().splitlines()))
    except FileNotFoundError:
        logger.error("Файл autos.txt не найден, создаю новый.")
        return []


def write_autos(autos: List[str]) -> None:
    """
    Перезаписывает файл autos.txt новыми данными.

    :param autos: Список строковых идентификаторов чатов, которые нужно записать.
    :return: None
    """
    with open("autos.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(autos))


# ------------------ Bot commands and handlers ------------------ #
async def start(_: Client, message: Message) -> None:
    """
    Обрабатывает команду /start. Если после команды указан аргумент 'donat',
    то отправляет сообщение о донатах и пересылает сообщение определённому пользователю.
    Иначе отвечает стандартным приветственным сообщением (START_MESSAGE).

    :param _: Объект клиента Pyrogram (не используется, но необходим для сигнатуры хендлера).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    try:
        logger.info(f"Получено сообщение: {message.text}")
        # Проверяем наличие дополнительного текста после /start
        if len(message.text.split()) > 1:
            text = message.text.split(" ", 1)[1]
            if len(text) > 3 and text.startswith("donat"):
                text = text[5:]
                await message.reply(DONAT_MESSAGE, reply_markup=get_donations_buttons())
                await message.forward("amnesiawho1")
        else:
            await message.reply(START_MESSAGE)
    except AttributeError as e:
        logger.error(f"Произошла ошибка: {e}. Возможно, message.text = {message.text}")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")


async def is_user_message_admin(message: Message) -> bool:
    """
    Проверяет, является ли пользователь, отправивший сообщение, администратором текущего чата.
    Также проверяет, есть ли пользователь в списке глобальных администраторов (из БД).

    :param message: Объект сообщения Pyrogram.
    :return: True, если статус пользователя ADMINISTRATOR/OWNER или если он числится в БД как админ; иначе False.
    """
    try:
        user = await bot.get_chat_member(message.chat.id, message.from_user.id)
    except pyrogram.errors.UserNotParticipant:
        return False
    return (
        user.status in (ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER)
        or message.from_user.id in db.get_admins()
    )


async def get_stats(_: Client, message: Message) -> None:
    """
    Генерирует и отправляет график статистики для текущего чата.
    Использует метод get_stats_graph из БД, который возвращает путь к файлу с графиком (или список путей).

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    result = db.get_stats_graph(message.chat.id)
    if isinstance(result, str):
        await message.reply_photo(result)
    elif isinstance(result, list):
        media = [InputMediaPhoto(media=img) for img in result]
        await message.reply_media_group(media)


async def gen_regex(_: Client, message: Message) -> None:
    """
    Генерирует регулярное выражение, объединяющее все запрещённые слова для текущего чата.
    Отправляет сгенерированный паттерн в ответ.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    keywords = get_keywords(message.chat.id) or ["слово"]
    pattern = r"(" + "|".join(keywords) + r")"
    await message.reply(pattern)


async def list_command(_: Client, message: Message) -> None:
    """
    Выводит список всех запрещённых слов (из глобального списка, без учёта чата).

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    try:
        bad_words = get_keywords()  # Если не передан chat_id, берём глобальный список
        await message.reply(f"```Запретки\n{'\n'.join(bad_words)}```")
    except Exception:
        await message.reply("Ошибка при обработке запроса.")


async def invert(_: Client, message: Message) -> None:
    """
    Удаляет диакритику (используя unidecode) и приводит текст к нижнему регистру.
    Затем отправляет преобразованный текст как ответ.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram с текстом.
    :return: None
    """
    text = " ".join(message.text.lower().strip().replace("/invert ", "").splitlines())
    await message.reply(unidecode.unidecode(text))


async def get_commons(_: Client, message: Message) -> None:
    """
    Получает наиболее часто (или наименее часто) встречающиеся слова в БД.
    Аргументы разбираются из текста сообщения по схеме ARG_DEFINITIONS (min_len, max_len, limit, reverse и т.д.).
    Далее вызывается метод get_most_common_word() из БД и отправляется результат.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram с аргументами после команды.
    :return: None
    """
    try:
        tokens = message.text.split()[1:]
        args = parse_arguments(tokens, ARG_DEFINITIONS)

        if args["min_len"] is not None and args["max_len"] is not None:
            if args["min_len"] > args["max_len"]:
                args["min_len"], args["max_len"] = args["max_len"], args["min_len"]

        result = db.get_most_common_word(
            args["min_len"], args["max_len"], args["limit"], args["reverse"]
        )

        await message.reply(str(result))

    except Exception as e:
        logger.error(f"Ошибка в get_commons: {e}")


async def check_command(client: Client, message: Message) -> None:
    """
    Команда для проверки пользователя через внешний API (FunStat).
    Если пользователь уже помечен как спамер (pending ban), отправляется соответствующее уведомление.
    Иначе — проверка по API.

    :param client: Объект клиента Pyrogram.
    :param message: Объект сообщения Pyrogram с текстом вида "/check_command <user_id или @username>".
    :return: None
    """
    try:
        user_id_str = message.text.split(" ")[1]
        # Проверяем, цифры ли это. Если нет — пытаемся запросить информацию через get_chat_member
        if not user_id_str.isdigit():
            user = await client.get_chat_member(message.chat.id, user_id_str)
            user_id = int(user.user.id)
        else:
            user_id = int(user_id_str)

        if user_id in db.get_pending_bans():
            await message.reply(
                "Этот пользователь помечен как спамер!",
                reply_markup=get_ban_button(user_id, message.id),
            )
            return
        result = await check_user(user_id)
        await message.reply(result if result else "Пользователь не найден.")
    except IndexError:
        await message.reply("Укажите имя пользователя после команды.")
    except Exception as e:
        await message.reply(f"Ошибка при обработке запроса. {e}")


async def on_new_member(_: Client, message: Message) -> None:
    """
    Обрабатывает событие добавления нового участника в чат.
    1) Если бот сам только что добавлен в чат, регистрирует чат в БД и отправляет приветственное сообщение.
    2) Если новый пользователь помечен как забаненный, предлагает админам сразу же его забанить.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram (с new_chat_members).
    :return: None
    """
    for new_member in message.new_chat_members:
        if new_member.is_self:
            if message.chat.id == "-1001515209846":
                await leave_chat(_, message)
            await start(_, message)
            db.add_chat(message.chat.id, message.chat.title)
            break

        if db.is_user_banned(new_member.id):
            reply_markup = InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton(
                            "🚫 Забанить",
                            callback_data=f"ban_{message.id}_{message.from_user.id}",
                        ),
                        InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
                    ]
                ]
            )
            await message.reply(
                "Пользователь помечен как спамер!\nНужно ли его забанить?",
                reply_markup=reply_markup,
            )


def search_keywords(text: Union[str, int], chat_id: Optional[int] = None) -> bool:
    """
    Ищет запрещенные слова и паттерны (спецсимволы, подозрительные конструкции) в тексте.
    Считает условный 'score', сравнивает с SPAM_THRESHOLD, если score >= порога — считается спамом.

    :param text: Текст сообщения (или некорректный тип, тогда бросится ошибка).
    :param chat_id: Идентификатор чата для использования конкретного списка запрещенных слов (опционально).
    :return: True, если найден спам; False в противном случае.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Текст должен быть непустой строкой")

    try:
        score = 0
        keywords = get_keywords(chat_id) or ["слово"]
        normalized_text = unidecode.unidecode(text.lower().strip())

        # Проверка запрещенных слов
        keyword_pattern = r"(" + "|".join(map(re.escape, keywords)) + r")"
        found_keywords = len(re.findall(keyword_pattern, normalized_text))
        score += found_keywords

        # Проверка специальных символов (каждое совпадение добавляет 2 к score)
        special_chars_found = sum(
            bool(re.search(pattern, text)) for pattern in get_special_patterns()
        )
        score += special_chars_found * 2

        # Подозрительные паттерны
        suspicious_patterns = [
            r"\b(прем|премиум|premium)\b.*?@\w+",
            r"@\w+.*?\b(прем|премиум|premium)\b",
            r"\b(тут|here)\b.*?@\w+",
            r"@\w+.*?\b(тут|here)\b",
            r"➡️.*?@\w+",
            r"@\w+.*?➡️",
        ]
        for pattern in suspicious_patterns:
            if re.search(pattern, normalized_text, re.IGNORECASE):
                score += 5

        return score >= SPAM_THRESHOLD

    except Exception as e:
        logger.error(f"Ошибка при поиске ключевых слов: {str(e)}")
        return False


async def set_threshold(_: Client, message: Message) -> None:
    """
    Команда для изменения глобальной переменной SPAM_THRESHOLD и обновления её в .env.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram с текстом вида "/set_threshold <число>".
    :return: None
    """
    try:
        new_threshold = float(message.text.split()[1])
        if new_threshold <= 0:
            await message.reply("Порог должен быть положительным числом!")
            return

        global SPAM_THRESHOLD
        SPAM_THRESHOLD = new_threshold

        env_path = os.path.join(os.path.dirname(__file__), ".env")
        with open(env_path, "r", encoding="utf-8") as f:
            lines = f.readlines()

        threshold_line = f"SPAM_THRESHOLD={new_threshold}\n"
        threshold_found = False

        for i, line in enumerate(lines):
            if line.startswith("SPAM_THRESHOLD="):
                lines[i] = threshold_line
                threshold_found = True
                break

        if not threshold_found:
            lines.append(threshold_line)

        with open(env_path, "w", encoding="utf-8") as f:
            f.writelines(lines)

        await message.reply(f"Новый порог установлен и сохранён: {SPAM_THRESHOLD}")
    except (IndexError, ValueError):
        await message.reply(
            f"Текущий порог: {SPAM_THRESHOLD}\nИспользование: /set_threshold [Число]"
        )
    except Exception as e:
        logger.error(f"Ошибка при установке порога: {str(e)}")
        await message.reply(f"Ошибка при установке порога: {str(e)}")


def highlight_banned_words(text: str, chat_id: Optional[int] = None) -> str:
    """
    Выделяет запрещённые слова в тексте, оборачивая их в тэги < >.
    Если список слов пуст, возвращает исходный текст без изменений.

    :param text: Исходный текст сообщения.
    :param chat_id: Идентификатор чата для получения конкретного списка слов (опционально).
    :return: Преобразованный текст, где все запрещенные слова обёрнуты в <>.
    """
    if not text or not isinstance(text, str):
        return text

    try:
        keywords = get_keywords(chat_id) or []
        if not keywords:
            return text

        pattern = r"\b(" + "|".join(map(re.escape, keywords)) + r")\b"

        def replacer(match):
            return f"<{match.group(0)}>"

        return re.sub(pattern, replacer, text, flags=re.IGNORECASE)
    except Exception as e:
        logger.error(f"Ошибка при выделении запрещенных слов: {str(e)}")
        return text


async def add_badword(_: Client, message: Message) -> None:
    """
    Добавляет новое слово в глобальный список запрещенных слов (в файл bad_words.txt).

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram, содержащее новое слово после команды.
    :return: None
    """
    word = " ".join(message.text.split(" ")[1:])
    with open("bad_words.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{unidecode.unidecode(word.lower())}")
    keywords = get_keywords()
    await message.reply(
        f"Добавлено слово: {word}\nТекущий список запрещенных слов:\n{', '.join(keywords)}"
    )


@lru_cache(maxsize=128)
def get_special_patterns() -> List[str]:
    """
    Возвращает список регулярных выражений для поиска особых (нетипичных) символов,
    например, редких Юникод-блоков, которые часто используются в спаме.

    :return: Список строк (паттерны регулярных выражений).
    """
    return [
        r"[\u0500-\u052F]",  # Доп. символы Кириллицы
        r"[\u0180-\u024F]",  # Расширенная латиница
        r"[\u1D00-\u1D7F]",  # Фонетические символы
        r"[\u1E00-\u1EFF]",  # Расширенная латиница (доп. формы)
        r"[\u1100-\u11FF]",  # Корейские символы (Hangul)
        r"[\uFF00-\uFFEF]",  # Полуширина и полноширина форм
    ]


async def menu_command(_: Client, message: Message) -> None:
    """
    Отправляет главное меню настроек бота (inline-кнопки).
    Команда недоступна в личных сообщениях.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    if message.chat.type == ChatType.PRIVATE:
        msg = await message.reply("Меню недоступно в личных сообщениях")
        await asyncio.sleep(5.0)
        await msg.delete()
        await message.delete()
        return
    await message.reply_text(
        "🔧 Главное меню настроек бота:", reply_markup=get_main_menu()
    )


def get_keywords(chat_id: Optional[int] = None) -> List[str]:
    """
    Возвращает общий список запрещённых слов (из файла bad_words.txt),
    а также слова, добавленные именно для указанного чата (если передан chat_id).

    :param chat_id: Идентификатор чата (опционально).
    :return: Список уникальных слов (в нижнем регистре, без пробелов).
    """
    try:
        with open("bad_words.txt", "r", encoding="utf-8") as f:
            main_words = unidecode.unidecode(
                f.read().lower().replace(" ", r"\s")
            ).splitlines()
        chat_keywords = db.get_chat_badwords(chat_id) if chat_id else []
        all_words = set(filter(None, main_words + chat_keywords))
        return list(all_words)
    except Exception as e:
        logger.error(f"Error reading keywords: {e}")
        return []


async def check_user(user_id: Optional[int] = None) -> Union[bool, Optional[str]]:
    """
    Проверяет пользователя (user_id) через FunStat API (https://funstat.org),
    чтобы выяснить, соответствует ли он критериям "проверенный".
    Если пользователь уже есть в БД verified_users, возвращает True.
    Если данные получены и пользователь старше 60 дней, записывает в verified_users и возвращает JSON.
    Иначе возвращает False.

    :param user_id: Идентификатор пользователя для проверки.
    :return: True (если уже есть в БД), JSON-строка (если записали как проверенного), False (иначе).
    """
    if not user_id:
        return False
    if db.is_user_verified(user_id):
        return True

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"https://funstat.org/api/v1/users/{user_id}/stats_min",
                headers={
                    "accept": "application/json",
                    "Authorization": f"Bearer {token}",
                },
            ) as response:
                result = await response.json()
                if response.status != 200:
                    logger.error(f"API вернул статус {response.status}")
                    return False

                first_msg_date_str = result.get("first_msg_date")
                if not first_msg_date_str:
                    return False

                first_msg_date = datetime.datetime.strptime(
                    first_msg_date_str, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.timezone.utc)
                now = datetime.datetime.now(datetime.timezone.utc)
                delta = now - first_msg_date

                if delta >= datetime.timedelta(days=60):
                    user_data = {
                        "first_msg_date": first_msg_date_str,
                        "messages_count": result.get("messages_count", 0),
                        "chats_count": result.get("chats_count", 0),
                    }
                    db.add_verified_user(user_id, user_data)
                    return json.dumps(user_data)
                return False
    except Exception as e:
        logger.error(f"Error checking user: {e}")
        return False


async def postbot_filter(_: Client, message: Message) -> None:
    """
    Фильтрует сообщения, отправленные через @PostBot:
    1) Пересылает сообщение в канал "amnesiawho1".
    2) Удаляет оригинал из чата.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    if message.via_bot and message.via_bot.username == "PostBot":
        await message.forward("amnesiawho1")
        await message.delete()


async def leave_chat(_: Client, message: Message) -> None:
    """
    Команда для покидания чата ботом.
    Если после команды указать chat_id, бот выйдет из конкретного чата,
    иначе — из текущего.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram, в котором может быть указан chat_id.
    :return: None
    """
    if len(message.text.split(" ", 1)) > 1:
        chat_id = message.text.split(" ")[1]
    else:
        chat_id = message.chat.id

    await bot.send_message(chat_id, "До свидания!")
    await bot.leave_chat(chat_id, delete=True)


async def send_notion(client: Client, message: Message) -> None:
    """
    Отправляет пользователю информационное сообщение (NOTION_MESSAGE),
    вместе с кнопкой для связи/поддержки.

    :param client: Объект клиента Pyrogram.
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    try:
        await message.reply(
            NOTION_MESSAGE, reply_markup=get_support_button(message.from_user.id)
        )
    except Exception as e:
        logger.error(e)


async def send_test(client: Client, message: Message) -> None:
    """
    Рассылает NOTION_MESSAGE во все активные чаты (из БД).
    Может быть использовано, например, для тестовой/административной рассылки.

    :param client: Объект клиента Pyrogram.
    :param message: Объект сообщения Pyrogram (отправившего команду).
    :return: None
    """
    for chat, title in db.get_all_chats():
        try:
            await client.send_message(
                chat,
                NOTION_MESSAGE,
                reply_markup=get_support_button(message.from_user.id),
            )
            await asyncio.sleep(1)
        except Exception as e:
            await message.reply(f"{chat, title, str(e)}")


def ensure_chat_exists(chat_id: int, chat_title: Optional[str] = None) -> None:
    """
    Проверяет, зарегистрирован ли чат в БД. Если нет — добавляет запись с chat_id и названием.

    :param chat_id: Идентификатор чата (int).
    :param chat_title: Название чата (str) или None.
    :return: None
    """
    db.cursor.execute("SELECT chat_id FROM chats WHERE chat_id = ?", (chat_id,))
    if not db.cursor.fetchone():
        db.cursor.execute(
            "INSERT INTO chats (chat_id, title) VALUES (?, ?)",
            (chat_id, chat_title or "Неизвестный чат"),
        )
        db.connection.commit()


# ------------------ Main message handler ------------------ #
async def main(client: Client, message: Message) -> None:
    """
    Основной обработчик входящих текстовых сообщений. Выполняет:
    1) Логирование сообщения,
    2) Проверку пользователя на pending_ban,
    3) Проверку, не идёт ли сейчас добавление нового запрещённого слова,
    4) Случайную отправку информационного сообщения (send_notion),
    5) Поиск спам-паттернов (search_keywords),
    6) Сохранение пользователя и сообщения в БД,
    7) При необходимости — вызов handle_spam.

    :param client: Объект клиента Pyrogram.
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    if not message.from_user:
        return
    try:
        await log_message(message)

        if await check_pending_ban(message):
            return

        if await handle_new_badword(message):
            return

        # Случайное уведомление (вероятность 1 к 2000)
        if randint(1, 2000) == 1:
            await send_notion(client, message)

        autos = read_autos()
        ensure_chat_exists(message.chat.id, message.chat.title)

        is_spam = search_keywords(message.text, message.chat.id)

        # Сохраняем/обновляем информацию о пользователе
        db.add_user(
            user_id=message.from_user.id,
            first_name=message.from_user.first_name,
            username=message.from_user.username,
        )

        # Формируем ссылку на сообщение (если у чата есть username)
        message_url = (
            f"https://t.me/{message.chat.username}/c/{message.id}"
            if message.chat.username
            else None
        )

        # Сохраняем сообщение в БД
        db.add_message(
            message.chat.id,
            message.from_user.id,
            highlight_banned_words(message.text, message.chat.id),
            is_spam,
            message_url,
        )

        # Если сообщение — спам
        if is_spam:
            await handle_spam(message, autos)
    except Exception as e:
        logger.exception(f"Error processing message: {e}")


async def log_message(message: Message) -> None:
    """
    Логирует полученное сообщение в формате:
    <chat_id> (<chat_username>) - <user_id>: <text> <link_info (если есть)>

    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    chat_info = f" - {message.chat.username}" if message.chat.username else ""
    link_info = (
        f"- https://t.me/{message.chat.username}/c/{message.id}"
        if message.chat.username
        else ""
    )
    msg_text = " ".join(message.text.splitlines()) if message.text else ""
    logger.info(
        f"{message.chat.id}{chat_info} - {message.from_user.id}: {msg_text} {link_info}"
    )


async def check_pending_ban(message: Message) -> bool:
    """
    Проверяет, находится ли пользователь в состоянии "ban_pending" (превысил лимит спам-предупреждений).
    Если да — отправляет сообщение для админов с кнопками бана и возвращает True, иначе False.

    :param message: Объект сообщения Pyrogram.
    :return: True, если пользователь уже помечен на бан; False иначе.
    """
    if message.from_user.id in db.get_pending_bans():
        await message.reply(
            "@admins Этот пользователь помечен как спамер! Будьте внимательнее!",
            reply_markup=get_users_ban_pending(message.from_user.id, message.id),
        )
        return True
    return False


async def handle_new_badword(message: Message) -> bool:
    """
    Если ранее была инициирована команда на добавление нового слова, ждём от пользователя ввода самого слова.
    После ввода добавляем слово в список запрещённых для текущего чата и сбрасываем флаг ожидания.

    :param message: Объект сообщения Pyrogram.
    :return: True, если слово было обработано и добавлено; False иначе.
    """
    if waiting_for_word.get(message.from_user.id):
        word = message.text.strip()
        success = db.add_chat_badword(message.chat.id, word, message.from_user.id)
        waiting_for_word[message.from_user.id] = False
        reply_text = (
            f"✅ Слово **{word}** добавлено в список запрещенных!\n\n"
            if success
            else "❌ Ошибка при добавлении слова"
        )
        markup = get_filter_settings_button() if success else None
        await message.reply(reply_text, reply_markup=markup)
        return True
    return False


async def handle_spam(message: Message, autos: List[str]) -> None:
    """
    Обрабатывает сообщение, распознанное как спам:
    1) Добавляет предупреждение в БД,
    2) Если пользователь — администратор, шутит,
    3) Если чат в списке autos, удаляет сообщение,
    4) Иначе предлагает админам забанить пользователя.

    :param message: Объект сообщения Pyrogram, распознанное как спам.
    :param autos: Список идентификаторов чатов, в которых настроен автоматический режим (без вопроса).
    :return: None
    """
    db.add_spam_warning(message.from_user.id, message.chat.id, message.text)

    # Если сообщение длинное (> 1000), то просто не продолжаем (может быть flood)
    if len(message.text) > 1000:
        return

    if await is_user_message_admin(message):
        await message.reply("Тебе не стыдно?")

    if str(message.chat.id) in autos:
        await message.delete()
    else:
        await message.reply(
            "Подозрительное сообщение!",
            reply_markup=get_ban_button(message.from_user.id, message.id),
        )


# ------------------ Autos settings ------------------ #
async def remove_autos(_: Client, message: Message) -> None:
    """
    Удаляет текущий чат из списка autos (автоматическая модерация).

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    autos = read_autos()
    try:
        autos.remove(str(message.chat.id))
        write_autos(autos)
        await message.reply("Авто удалено!")
    except ValueError:
        await message.reply("Этого чата нет в списке авто.")


async def search(_: Client, message: Message) -> None:
    try:
        result = db.search(message.text.split()[1::])
        if not result:
            result = "ничего("
        await message.reply(result)
    except Exception as e:
        logger.error("Search error: " + str(e))


async def get_autos(_: Client, message: Message) -> None:
    """
    Выводит список всех чатов, занесённых в autos.txt.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    autos = read_autos()
    await message.reply("\n".join(autos) if autos else "Список пуст.")


async def add_autos(_: Client, message: Message) -> None:
    """
    Добавляет текущий чат в список autos (автоматическая модерация).
    Если он уже есть — выводит сообщение, что чат уже в списке.

    :param _: Объект клиента Pyrogram (не используется).
    :param message: Объект сообщения Pyrogram.
    :return: None
    """
    autos = read_autos()
    if str(message.chat.id) not in autos:
        autos.append(str(message.chat.id))
        write_autos(autos)
        msg = await message.reply("Чат добавлен!")
        await asyncio.sleep(15)
        await message.delete()
        await msg.delete()
    else:
        await message.reply("Чат уже есть в списке авто!")
