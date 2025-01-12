import asyncio
import datetime
import json
import os
import re
from functools import lru_cache
from typing import List, Optional

import aiohttp
import unidecode
from pyrogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from src.constants import SPAM_THRESHOLD, START_MESSAGE, token, waiting_for_word
from src.database import db
from src.markups.markups import (
    get_ban_button,
    get_filter_settings_button,
    get_main_menu,
)
from src.utils.logger_config import logger


async def start(_, message):
    await message.reply(START_MESSAGE)


async def gen_regex(_, message):
    keywords = get_keywords() or ["слово"]

    pattern = r"(" + "|".join(keywords) + r")"
    await message.reply(pattern)


async def list_command(_, message) -> None:
    """Команда для вывода списка запрещенных слов."""
    try:
        bad_words = get_keywords()
        await message.reply(f"```Запретки\n{'\n'.join(bad_words)}```")
    except Exception:
        await message.reply("Ошибка при обработке запроса.")


async def invert(_, message):
    await message.reply(unidecode.unidecode(message.text.split("")))


async def check_command(_, message) -> None:
    """Команда для проверки пользователя через FunStat API."""
    try:
        user_id = message.text.split(" ")[1]
        if not user_id.isdigit():
            user = await _.get_chat_member(message.chat.id, user_id)
            user_id = int(user.user.id)
        else:
            user_id = int(user_id)
        result = await check_user(user_id) or "Пользователь не найден."
        await message.reply(result)
    except IndexError:
        await message.reply("Укажите имя пользователя после команды.")
    except Exception as e:
        await message.reply(f"Ошибка при обработке запроса. {e}")


async def on_new_member(_, message):
    for new_member in message.new_chat_members:
        if new_member.is_self:
            await message.reply("Привет! Я был добавлен в этот чат. Чем могу помочь?")
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
                "Пользователь помечен как спамер!Нужно ли его забанить",
                reply_markup=reply_markup,
            )


def search_keywords(text: str, chat_id: int | None = None) -> bool:
    """
    Ищет запрещенные слова и специальные символы в тексте.
    Учитывает слова конкретного чата, если указан chat_id.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Текст должен быть непустой строкой")

    try:
        score = 0
        keywords = get_keywords(chat_id) or ["слово"]

        normalized_text = unidecode.unidecode(text.lower())
        keyword_pattern = r"\b(" + "|".join(map(re.escape, keywords)) + r")\b"
        found_keywords = len(re.findall(keyword_pattern, normalized_text))

        score += found_keywords

        special_chars_found = 0
        for pattern in get_special_patterns():
            if re.search(pattern, text):
                special_chars_found += 2

        score += special_chars_found * 1.5
        return score >= SPAM_THRESHOLD

    except Exception as e:
        logger.error(f"Ошибка при поиске ключевых слов: {str(e)}")
        return False


async def set_threshold(_, message):
    """Команда для изменения порога спама."""
    try:
        if not await check_is_admin(_, message):
            return

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


async def menu_command(_, message):
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
                f.read().lower().replace(" ", "")
            ).splitlines()

        if chat_id:
            chat_keywords = db.get_chat_badwords(chat_id)
            keywords.extend(chat_keywords)

        return list(filter(None, set(keywords)))
    except Exception as e:
        logger.error(f"Error reading keywords: {e}")
        return []


async def check_user(user_id: int | None = None) -> bool | Optional[str]:
    """
    Проверяет пользователя через FunStat API и сохраняет результаты в БД.
    """
    if not user_id:
        return

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


async def check_is_admin(_, message) -> bool:
    """
    Проверяет, что пользователь, отправивший сообщение, является админом или создателем.
    Если нет — отправляет ответ и возвращает False.
    """
    user = await _.get_chat_member(message.chat.id, message.from_user.id)
    message.from_user.restrictions
    if not user.privileges:
        msg = await message.reply(
            f"Вы не являетесь администратором или основателем! {message.from_user.status.value}"
        )
        await asyncio.sleep(3.0)
        await _.delete_messages(message.chat.id, [msg.id, message.id])

        return False
    return True


async def main(_, message) -> None:
    """
    Обрабатывает входящие текстовые сообщения, проверяет наличие запрещенных слов.
    Если слова найдены, удаляет сообщение и логирует.
    """
    try:
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

        text = message.text
        logger.info(
            f"Processing message from {message.chat.id}{f' - {message.chat.username}' if message.chat.username else ''} - {message.from_user.id}: {' '.join(text.splitlines())}"
        )

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
        )
        db.update_stats(message.chat.id, messages=True)
        if is_spam:
            is_user_valid = await check_user(
                message.from_user.id if message.from_user.id != 5957115070 else None
            )

            if is_user_valid == "False" and message.from_user.id != 5957115070:
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
    if not await check_is_admin(_, message):
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


async def check_is_admin_callback(_, callback_query) -> bool:
    """
    Проверяет, что пользователь, нажавший кнопку, является админом или создателем.
    Если нет — отправляет ответ и возвращает False.
    """
    chat_id = callback_query.message.chat.id
    chat_member = await _.get_chat_member(chat_id, callback_query.from_user.id)
    if chat_member.status.value not in ["administrator", "owner"]:
        await callback_query.answer(
            "Вы не являетесь администратором или основателем!", show_alert=True
        )
        return False
    return True
