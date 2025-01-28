import asyncio
import datetime
import json
import os
import re
from functools import lru_cache
from typing import AnyStr, List, Optional

import aiohttp
import pyrogram
import unidecode
from pyrogram.client import Client
from pyrogram.enums import ChatMemberStatus
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup, Message

from src.constants import (
    SPAM_THRESHOLD,
    START_MESSAGE,
    DONAT_MESSAGE,
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


async def start(_, message: Message):
    try:
        if not logger:
            raise ValueError("Logger не инициализирован")

        logger.info(f"Получено сообщение: {message.text}")

        if len(message.text.split()) > 1:
            text = message.text.split(" ", 1)[1]
            if len(text) > 3 and text.startswith("donat"):
                text = text[5:]
                await message.reply(DONAT_MESSAGE, reply_markup=get_donations_buttons())
        else:
            await message.reply(START_MESSAGE)
    except AttributeError as e:
        logger.error(f"Произошла ошибка: {e}. Возможно, message.text = {message.text}")
    except Exception as e:
        logger.error(f"Произошла ошибка: {e}")



async def is_admin(message: Message) -> bool:
    user = await bot.get_chat_member(message.chat.id, message.from_user.id)
    return bool(
        user.status in [ChatMemberStatus.ADMINISTRATOR, ChatMemberStatus.OWNER]
    ) or bool(message.from_user.id in db.get_admins())


async def get_stats(_, message: Message) -> None:
    result = db.get_stats_graph(message.chat.id)
    if isinstance(result, str):
        await message.reply_photo(result)
    elif isinstance(result, List[str]):  # type: ignore
        media = []
        for img in result:
            media.append(pyrogram.types.InputMediaPhoto(media=img))
        await message.reply_media_group(media)


async def gen_regex(_, message):
    keywords = get_keywords(message.chat.id) or ["слово"]

    pattern = r"(" + "|".join(keywords) + r")"
    await message.reply(pattern)


async def list_command(_, message) -> None:
    """Команда для вывода списка запрещенных слов."""
    try:
        bad_words = get_keywords()
        await message.reply(f"```Запретки\n{'\n'.join(bad_words)}```")
    except Exception:
        await message.reply("Ошибка при обработке запроса.")


async def invert(_, message: Message) -> None:
    await message.reply(
        unidecode.unidecode(
            " ".join(message.text.lower().strip().replace("/invert ", "").splitlines())
        )
    )


async def get_commons(_, message: Message):
    try:
        text = message.text.split(" ")

        # Проверяем наличие нужных элементов в списке
        min_len = int(text[1]) if len(text) > 1 and text[1].isdigit() else 3
        max_len = int(text[2]) if len(text) > 2 and text[2].isdigit() else 10

        # Здесь вызывается ваша функция базы данных
        await message.reply(db.get_most_common_word(min_len, max_len))
    except Exception as e:
        logger.error(e)


async def check_command(client: pyrogram.client.Client, message: Message) -> None:
    """Команда для проверки пользователя через FunStat API."""
    try:
        user_id = message.text.split(" ")[1]
        if not user_id.isdigit():
            user = await client.get_chat_member(message.chat.id, user_id)
            user_id = int(user.user.id)
        else:
            user_id = int(user_id)
        if user_id in db.get_pending_bans():
            await message.reply(
                "Этот пользователь помечен как спамер!",
                reply_markup=get_ban_button(user_id, message.id),
            )
            return
        result = await check_user(user_id)
        await message.reply(result if result else "Пользователь не найден.")  # type: ignore
    except IndexError:
        await message.reply("Укажите имя пользователя после команды.")
    except Exception as e:
        await message.reply(f"Ошибка при обработке запроса. {e}")


async def on_new_member(_, message: Message):
    for new_member in message.new_chat_members:
        if new_member.is_self:
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
                        InlineKeyboardButton(
                            text="❌ Отмена",
                            callback_data="cancel",
                        ),
                    ],
                ]
            )
            await message.reply(
                "Пользователь помечен как спамер!\nНужно ли его забанить",
                reply_markup=reply_markup,
            )


def search_keywords(text: AnyStr | int, chat_id: Optional[int] | None = None) -> bool:
    """
    Ищет запрещенные слова, специальные символы и подозрительные паттерны в тексте.
    Учитывает слова конкретного чата, если указан chat_id.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Текст должен быть непустой строкой")

    try:
        score = 0
        keywords = get_keywords(chat_id) or ["слово"]

        normalized_text = unidecode.unidecode(text.lower().strip())
        keyword_pattern = r"(" + "|".join(map(re.escape, keywords)) + r")"
        found_keywords = len(re.findall(keyword_pattern, normalized_text))

        score += found_keywords

        special_chars_found = 0
        for pattern in get_special_patterns():
            if re.search(pattern, text):
                special_chars_found += 2

        score += special_chars_found * 2

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


async def set_threshold(_, message):
    """Команда для изменения порога спама."""
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

        await message.reply(f"Новый порог установлен и сохранен: {SPAM_THRESHOLD}")

    except (IndexError, ValueError):
        await message.reply(
            f"Текущий порог: {SPAM_THRESHOLD}Использование /set_threshold [Число]"
        )
    except Exception as e:
        logger.error(f"Ошибка при установке порога: {str(e)}")
        await message.reply(f"Ошибка при установке порога: {str(e)}")


def highlight_banned_words(text: str, chat_id: int | None = None) -> str:
    """
    Обводит запрещенные слова в тексте тегами.

    Args:
        text (str): Исходный текст
        chat_id (int, optional): ID чата для получения специфичных банвордов

    Returns:
        str: Текст с выделенными запрещенными словами
    """
    if not text or not isinstance(text, str):
        return text

    try:
        keywords = get_keywords(chat_id) or []

        if not keywords:
            return text

        pattern = r"\b(" + "|".join(map(re.escape, keywords)) + r")\b"

        def replace(match):
            return f"<{match.group(0)}>"

        result = re.sub(pattern, replace, text, flags=re.IGNORECASE)

        return result

    except Exception as e:
        logger.error(f"Ошибка при выделении запрещенных слов: {str(e)}")
        return text


async def add_badword(_, message):
    word = " ".join(message.text.split(" ")[1:])
    with open("bad_words.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{unidecode.unidecode(word.lower())}")
    keywords = get_keywords()
    await message.reply(
        f"Добавлено слово: {word}\nТекущий список запрещенных слов:\n{', '.join(keywords)}"
    )


@lru_cache(maxsize=128)
def get_special_patterns() -> List[str]:
    """Возвращает список скомпилированных регулярных выражений для специальных символов."""
    return [
        r"[\u0500-\u052F]",
        r"[\u0180-\u024F]",
        r"[\u1D00-\u1D7F]",
        r"[\u1E00-\u1EFF]",
        r"[\u0300-\u036F]",
        r"[\u1100-\u11FF]",
        r"[\uFF00-\uFFEF]",
    ]


async def menu_command(_, message: Message):
    if message.chat.type == pyrogram.enums.ChatType.PRIVATE:
        msg = await message.reply("Меню недоступно в личных сообщениях")
        await asyncio.sleep(5.0)
        await msg.delete()
        await message.delete()
        return
    await message.reply_text(
        "🔧 Главное меню настроек бота:", reply_markup=get_main_menu()
    )


def get_keywords(chat_id: int | None = None) -> List[str]:
    """
    Читает список запрещенных слов.
    Если указан chat_id, добавляет к общему списку слова конкретного чата.
    """
    try:
        with open("bad_words.txt", "r", encoding="utf-8") as f:
            keywords = unidecode.unidecode(
                f.read().lower().replace(" ", r"\s")
            ).splitlines()

        if chat_id:
            chat_keywords = db.get_chat_badwords(chat_id)
            keywords.extend(chat_keywords)
        result = list(filter(None, set(keywords)))
        return result
    except Exception as e:
        logger.error(f"Error reading keywords: {e}")
        return []


async def check_user(user_id: int | None = None) -> bool | Optional[str]:
    """
    Проверяет пользователя через FunStat API и сохраняет результаты в БД.
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


async def postbot_filter(_, message: Message):
    if message.via_bot.username == "PostBot":
        await message.forward("amnesiawho1")
        await message.delete()


async def leave_chat(_, message: Message):
    await bot.leave_chat(message.chat.id)


async def send_notion(client: Client, message: Message):
    try:
        text = "🤖 Мой антиспам-бот защищает ваш чат от спама и хаоса. \nЕсли он вам помогает, любая копеечка поддержит его развитие и новые фишки. 🛡️✨\nСпасибо за вашу помощь! ❤️"
        await message.reply(text, reply_markup=get_support_button(message.from_user.id))
    except Exception as e:
        logger.error(e)


async def main(_, message: Message) -> None:
    """
    Обрабатывает входящие текстовые сообщения, проверяет наличие запрещенных слов.
    Если слова найдены, удаляет сообщение и логирует.
    """
    if not message.from_user:
        return
    try:
        text = message.text
        logger.info(
            f"{message.chat.id}{f' - {message.chat.username}' if message.chat.username else ''} "
            f"- {message.from_user.id}: {' '.join(text.splitlines())} "
            f"{f'- https://t.me/{message.chat.username}/c/{message.id}' if message.chat.username else ''}"
        )
        if message.from_user.id in db.get_pending_bans():
            await message.reply(
                "@admins Этот пользователь помечен как спамер! Будьте внимательнее!",
                reply_markup=get_users_ban_pending(message.from_user.id, message.id),
            )
            return
        if waiting_for_word[message.from_user.id]:
            word = message.text.strip()
            chat_id = message.chat.id
            success = db.add_chat_badword(chat_id, word, message.from_user.id)
            waiting_for_word[message.from_user.id] = False
            if success:
                await message.reply(
                    f"✅ Слово **{word}** добавлено в список запрещенных для этого чата!\n\n",
                    reply_markup=get_filter_settings_button(),
                )
            else:
                await message.reply("❌ Ошибка при добавлении слова")
            return

        try:
            with open("autos.txt", "r", encoding="utf-8") as f:
                autos = f.read().splitlines()
        except FileNotFoundError:
            logger.error("File autos.txt not found")
            autos = []

        def ensure_chat_exists(chat_id: int, chat_title: str | None = None):
            db.cursor.execute("SELECT chat_id FROM chats WHERE chat_id = ?", (chat_id,))
            if not db.cursor.fetchone():
                db.cursor.execute(
                    "INSERT INTO chats (chat_id, title) VALUES (?, ?)",
                    (chat_id, chat_title or "Неизвестный чат"),
                )
                db.connection.commit()

        ensure_chat_exists(message.chat.id, message.chat.title)

        is_spam = search_keywords(text, message.chat.id)

        db.add_user(
            user_id=message.from_user.id,
            first_name=message.from_user.first_name,
            username=message.from_user.username if message.from_user.username else None,
        )
        db.add_message(
            message.chat.id,
            message.from_user.id,
            highlight_banned_words(message.text, message.chat.id),
            is_spam,
            (
                "https://t.me/" + message.chat.username + "/c/" + str(message.id)
                if message.chat.username
                else None
            ),
        )
        db.update_stats(message.chat.id, messages=True)
        if is_spam:
            if await is_admin(message):
                await message.reply("Тебе не стыдно?")
                return
            await message.forward("amnesiawho1")
            if len(message.text) > 1000:
                return

            if str(message.chat.id) in autos:
                await message.delete()
            else:
                await message.reply(
                    "Подозрительное сообщение!",
                    reply_markup=get_ban_button(message.from_user.id, message.id),
                )
            db.add_spam_warning(message.from_user.id, message.chat.id, message.text)

            db.update_stats(message.chat.id, deleted=True)

    except Exception as e:
        logger.exception(f"Error processing message: {e}")


async def remove_autos(_, message):
    autos = open("autos.txt", "r", encoding="utf-8").read().split("\n")
    autos.remove(str(message.chat.id))
    with open("autos.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(autos))
    await message.reply("Авто удалено!")


async def get_autos(_, message):
    autos = open("autos.txt", "r", encoding="utf-8").read().split("\n")
    await message.reply("\n".join(autos))


async def add_autos(_, message):
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
