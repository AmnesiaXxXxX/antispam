import asyncio
import datetime
import json
import os
import re
import time
from collections import defaultdict
from functools import lru_cache
from typing import List, Optional

import aiohttp
import pyrogram
import pyrogram.errors
import unidecode
from dotenv import load_dotenv
from pyrogram import Client, filters  
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)

from database import Database
from logger_config import logger


load_dotenv()

db = Database("antispam.db")


token = os.getenv("TOKEN") or exit("TOKEN is not set")
bot_token = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN is not set")
api_id = os.getenv("API_ID") or exit("API_ID is not set")
api_hash = os.getenv("API_HASH") or exit("API_HASH is not set")

filter_settings_markup = InlineKeyboardMarkup(
    [
        [
            InlineKeyboardButton(
                "🔍 Добавить запрещенное слово", callback_data="add_badword"
            )
        ],
        [
            InlineKeyboardButton(
                "🗑 Удалить запрещенное слово", callback_data="remove_badword"
            )
        ],
        [
            InlineKeyboardButton("◀️ Назад", callback_data="settings"),
            InlineKeyboardButton("📋 Вывод списка слов", callback_data="list_badwords"),
        ],
    ]
)

START_MESSAGE = """

Великий Фильтр - это современное решение для предотвращения спама и управления чатами. С помощью этого бота вы сможете обеспечить чистоту и безопасность вашего сообщества, не прибегая к ручной модерации каждый раз.





- **Фильтрация спама и ключевых слов**:  
  Мощные алгоритмы автоматически блокируют нежелательные сообщения и ключевые слова, упрощая общение участников.  
- **Защита от нежелательных символов**:  
  Определяет и блокирует запрещенные символы, включая скрытые комбинации, часто используемые для обхода стандартных фильтров.  
- **Проверка новых участников**:  
  Анализ профилей новых пользователей при вступлении помогает выявить и ограничить доступ подозрительным аккаунтам.


- **Удаление и блокировка**:  
  Позволяет автоматически или вручную удалять сообщения и блокировать нарушителей. Это обеспечивает соблюдение правил чата.  
- **Пересылка подозрительных сообщений**:  
  Подозрительные сообщения отправляются модераторам на проверку, что помогает снизить вероятность ложных блокировок.


- **Удобный интерфейс**:  
  Бот предоставляет интуитивно понятные кнопки и меню для управления его функциями.  
- **Регулировка чувствительности фильтров**:  
  Подстройте уровень фильтрации под размер и специфику вашего сообщества.


- **Отслеживание активности**:  
  Бот собирает данные об активности участников и нарушениях, создавая подробные отчёты для анализа.  
- **Динамическая статистика**:  
  Анализ данных помогает выявить проблемные зоны и оптимизировать управление чатом.


- **Использование SQLite**:  
  Легковесная база данных надёжно сохраняет настройки и логи, обеспечивая долгосрочное хранение данных.


- **Администрирование с защитой**:  
  Только администраторы имеют доступ к управлению ботом, а пользовательские данные защищены на всех этапах обработки. Это гарантирует высокий уровень безопасности.


- **Асинхронная работа**:  
  Бот обрабатывает множество запросов одновременно, что обеспечивает высокую производительность даже в крупных сообществах.  
- **Интеграция с API и кэширование**:  
  Использует кэширование для ускорения работы и поддерживает взаимодействие с внешними сервисами через API.


Великий Фильтр - это идеальный выбор для модерирования чатов любых масштабов. Его возможности и гибкость настройки позволяют адаптировать работу бота под потребности вашего сообщества, обеспечивая комфорт и безопасность для всех участников.


"""
WORDS_PER_PAGE = 5  



bot = Client(
    "bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
)


SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD", "3"))  
waiting_for_word = defaultdict(bool)


def get_main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="cancel")],
        ]
    )


@bot.on_message(filters.command("menu"))
async def menu_command(client, message):
    await message.reply_text(
        "🔧 Главное меню настроек бота:", reply_markup=get_main_menu()
    )


@bot.on_callback_query(filters.regex(r"^remove_badword"))
async def remove_badword_handler(client: Client, callback_query: CallbackQuery):
    if not await check_is_admin_callback(client, callback_query):
        return

    page = 0
    if "_" in callback_query.data:
        page = int(callback_query.data.split("_")[1])

    chat_id = callback_query.message.chat.id

    
    words = db.get_chat_badwords(chat_id)
    total_pages = (len(words) - 1) // WORDS_PER_PAGE

    
    keyboard = []
    start_idx = page * WORDS_PER_PAGE
    end_idx = start_idx + WORDS_PER_PAGE

    for word in words[start_idx:end_idx]:
        keyboard.append(
            [
                InlineKeyboardButton(
                    f"❌ {word}", callback_data=f"del_word_{chat_id}_{word}"
                )
            ]
        )

    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️", callback_data=f"remove_badword_{page-1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton("➡️", callback_data=f"remove_badword_{page+1}")
        )
    if nav_buttons:
        keyboard.append(nav_buttons)

    
    keyboard.append([InlineKeyboardButton("◀️ Назад", callback_data="filter_settings")])

    markup = InlineKeyboardMarkup(keyboard)

    text = f"📝 Выберите слово для удаления (страница {page + 1}/{total_pages + 1}):"

    if callback_query.message.text != text:
        await callback_query.message.edit_text(text, reply_markup=markup)
    else:
        await callback_query.message.edit_reply_markup(markup)


@bot.on_callback_query(filters.regex(r"^del_word_"))
async def delete_word_handler(client: Client, callback_query: CallbackQuery):
    if not await check_is_admin_callback(client, callback_query):
        return

    try:
        _, chat_id, word = callback_query.data.split("_", 2)
        chat_id = int(chat_id)

        
        db.cursor.execute(
            "DELETE FROM chat_badwords WHERE chat_id = ? AND word = ?", (chat_id, word)
        )
        db.connection.commit()

        await callback_query.answer(f"Слово '{word}' удалено!")
        
        await remove_badword_handler(client, callback_query)

    except Exception as e:
        logger.error(f"Error deleting word: {e}")
        await callback_query.answer("Ошибка при удалении слова")


@bot.on_callback_query(filters.regex(r"ban_user_(\d+)_(\d+)"))
async def ban_user_callback(client: Client, callback_query: CallbackQuery):
    try:
        callback_query.data = callback_query.data.replace("ban_user_", "")
        msg_id = int(callback_query.data.split("_")[1])
        user_id = int(callback_query.data.split("_")[0])
        chat_id = callback_query.message.chat.id
        target = await client.get_chat_member(chat_id, user_id)

        
        if not await check_is_admin_callback(client, callback_query):
            return

        
        if user_id != 5957115070:
            if target.status.value in ["administrator", "owner"]:
                await callback_query.answer(
                    "Цель является администратором, не могу забанить(", show_alert=True
                )
                return
            else:
                await client.ban_chat_member(chat_id, user_id)
                db.update_stats(chat_id, banned=True)
        else:
            await callback_query.answer(
                "Ты уверен что себя хочешь забанить?", show_alert=True
            )
            return

        await callback_query.answer("Забанен!", show_alert=True)
        await client.delete_messages(chat_id, [msg_id, callback_query.message.id])
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        await callback_query.answer(
            "Ошибка при попытке забанить пользователя", show_alert=True
        )


@bot.on_callback_query()
async def callback_query(client: Client, callback_query: CallbackQuery):
    data = callback_query.data
    global filter_settings_markup
    if data == "stats":
        
        stats = db.get_stats(callback_query.message.chat.id)
        await callback_query.message.reply(
            f"📊 Статистика чата:\n\n"
            f"Всего сообщений: {stats[0]}\n"
            f"Удалено сообщений: {stats[1]}\n"
            f"Всего пользователей: {stats[2]}\n"
            f"Заблокировано: {stats[3]}"
        )
    if data == "list_badwords":
        chat_id = callback_query.message.chat.id
        words = db.get_chat_badwords(chat_id)
        if not words:
            await callback_query.message.edit_text(
                "Список запрещенных слов пуст.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("◀️ Назад", callback_data="filter_settings")]]
                ),
            )
        else:
            text = "📋 Список запрещенных слов:\n\n" + "\n".join(words)
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("◀️ Назад", callback_data="filter_settings")]]
                ),
            )
    elif data == "cancel":
        chat_id = callback_query.message.chat.id
        try:
            chat_member = await client.get_chat_member(
                chat_id, callback_query.from_user.id
            )
        except pyrogram.errors.UserNotParticipant:
            await callback_query.answer(
                "Вы не являетесь участником чата", show_alert=True
            )
        if chat_member.status.value in ["administrator", "owner"]:
            await callback_query.message.delete()
        else:
            await callback_query.answer(
                "Вы не являетесь администратором или основателем!", show_alert=True
            )
    elif data == "delete":
        
        if not await check_is_admin_callback(client, callback_query):
            await callback_query.answer(
                "У вас нет прав для выполнения этого действия!", show_alert=True
            )
            return

        # Удаление сообщенийF
        messages_to_delete = [
            callback_query.message.reply_to_message.id,
            callback_query.message.id,
        ]

        await client.delete_messages(callback_query.message.chat.id, messages_to_delete)
        db.update_stats(callback_query.message.chat.id, deleted=True)
        logger.info(
            f"Messages {messages_to_delete} deleted in chat {callback_query.message.chat.id}"
        )
    elif data == "settings":
        settings_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔍 Настройки фильтрации", callback_data="filter_settings"
                    )
                ],
                [
                    InlineKeyboardButton(
                        "⏰ Автоочистка", callback_data="autoclean_settings"
                    )
                ],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")],
            ]
        )
        await callback_query.message.edit_text(
            "⚙️ Настройки бота:", reply_markup=settings_markup
        )

    elif data == "channels_list":
        channels = db.get_all_channels()
        if not channels:
            text = "Список каналов пуст"
        else:
            text = "📋 Список подключенных каналов:\n\n"
            for chat_id, title in channels:
                text += f"• {title} (ID: {chat_id})\n"

        await callback_query.message.edit_text(
            text,
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
            ),
        )

    elif data == "back_to_main":
        await callback_query.message.edit_text(
            "🔧 Главное меню настроек бота:", reply_markup=get_main_menu()
        )

    elif data == "autoclean_settings":
        
        try:
            with open("autos.txt", "r", encoding="utf-8") as f:
                autos = f.read().splitlines()
        except FileNotFoundError:
            autos = []

        is_auto = str(callback_query.message.chat.id) in autos
        status = "✅ Включена" if is_auto else "❌ Выключена"

        autoclean_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔄 Переключить автомодерацию", callback_data="toggle_autoclean"
                    )
                ],
                [InlineKeyboardButton("◀️ Назад", callback_data="settings")],
            ]
        )

        await callback_query.message.edit_text(
            f"⚙️ Настройки автомодерации\n\n"
            f"Текущий статус: {status}\n\n"
            f"При включенной автомодерации подозрительные сообщения "
            f"будут удаляться автоматически, без подтверждения администратора.",
            reply_markup=autoclean_markup,
        )

    elif data == "toggle_autoclean":
        if not await check_is_admin_callback(client, callback_query):
            return

        chat_id = str(callback_query.message.chat.id)
        try:
            with open("autos.txt", "r", encoding="utf-8") as f:
                autos = f.read().splitlines()
        except FileNotFoundError:
            autos = []

        if chat_id in autos:
            autos.remove(chat_id)
            status = "❌ Выключена"

        else:
            autos.append(chat_id)
            status = "✅ Включена"

        with open("autos.txt", "w", encoding="utf-8") as f:
            f.write("\n".join(autos))
        autoclean_markup = InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔄 Переключить автомодерацию", callback_data="toggle_autoclean"
                    )
                ],
                [InlineKeyboardButton("◀️ Назад", callback_data="settings")],
            ]
        )
        await callback_query.message.edit_text(
            f"⚙️ Настройки автомодерации\n\n"
            f"Текущий статус: {status}\n\n"
            f"При включенной автомодерации подозрительные сообщения "
            f"будут удаляться автоматически, без подтверждения администратора.",
            reply_markup=autoclean_markup,
        )
        await callback_query.answer(f"Автомодерация {status}!", show_alert=True)
    elif data == "filter_settings":
        await callback_query.message.edit_text(
            "⚙️ Настройки фильтрации:", reply_markup=filter_settings_markup
        )

    elif data == "add_badword":
        if not await check_is_admin_callback(client, callback_query):
            return

        waiting_for_word[callback_query.from_user.id] = True
        await callback_query.message.edit_text(
            "📝 Отправьте слово, которое хотите добавить в список запрещенных.\n"
            "Для отмены нажмите кнопку ниже.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_word")]]
            ),
        )

    elif data == "cancel_add_word":
        waiting_for_word[callback_query.from_user.id] = False

        await callback_query.message.edit_text(
            "⚙️ Настройки фильтрации:", reply_markup=filter_settings_markup
        )



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



def get_keywords(chat_id: int = None) -> List[str]:
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
                "Пользователь помечен как спамер!" "Нужно ли его забанить",
                reply_markup=reply_markup,
            )
            
def highlight_banned_words(text: str, chat_id: int = None) -> str:
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
<<<<<<< HEAD

        # Если нет запрещенных слов, возвращаем исходный текст
        if not keywords:
            return text

        # Создаем паттерн для поиска слов
        pattern = r"\b(" + "|".join(map(re.escape, keywords)) + r")\b"

        # Заменяем найденные слова, оборачивая их в теги
        def replace(match):
            return f"<{match.group(0)}>"

        # Выполняем замену с учетом регистра
=======
        
        
        if not keywords:
            return text
            
        
        pattern = r'\b(' + '|'.join(map(re.escape, keywords)) + r')\b'
        
        
        def replace(match):
            return f"<{match.group(0)}>"
            
        
>>>>>>> a53e11fce995d431be9bea2ffb0b994581498aac
        result = re.sub(pattern, replace, text, flags=re.IGNORECASE)
        
        return result
        
    except Exception as e:
        logger.error(f"Ошибка при выделении запрещенных слов: {str(e)}")
        return text

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


def search_keywords(text: str, chat_id: int = None) -> bool:
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
<<<<<<< HEAD

        # Добавляем баллы за найденные ключевые слова
=======
        
        
>>>>>>> a53e11fce995d431be9bea2ffb0b994581498aac
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


@bot.on_message(filters.text & filters.command("set_threshold"))
async def set_threshold(client: Client, message: Message):
    """Команда для изменения порога спама."""
    try:
        if not await check_is_admin(client, message):
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
            f"Текущий порог: {SPAM_THRESHOLD}" f"Использование /set_threshold [Число]"
        )
    except Exception as e:
        logger.error(f"Ошибка при установке порога: {str(e)}")
        await message.reply(f"Ошибка при установке порога: {str(e)}")



@bot.on_message(filters.text & filters.command(["start"]))
async def start(client: Client, message: Message):
    await message.reply(START_MESSAGE)


@bot.on_message(filters.text & filters.command(["gen_regex"]))
async def gen_regex(client: Client, message: Message):
    keywords = get_keywords() or ["слово"]
    
    pattern = r"(" + "|".join(keywords) + r")"
    await message.reply(pattern)


@bot.on_message(filters.text & filters.command(["invert"]))
async def invert(client: Client, message: Message):
    await message.reply(unidecode.unidecode(message.text.split("")))



@bot.on_message(filters.text & filters.command(["list"]))
async def list_command(client: Client, message: Message) -> None:
    """Команда для вывода списка запрещенных слов."""
    try:
        bad_words = get_keywords()
        await message.reply(f"```Запретки\n{"\n".join(bad_words)}```")
    except Exception:
        await message.reply("Ошибка при обработке запроса.")



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
        )  
        await message.reply(result)
    except IndexError:
        await message.reply("Укажите имя пользователя после команды.")
    except Exception as e:
        await message.reply(f"Ошибка при обработке запроса. {e}")


<<<<<<< HEAD
# Функция для создания кнопок с баном и отменой
=======
async def check_is_admin(client: Client, message: Message) -> bool:
    """
    Проверяет, что пользователь, отправивший сообщение, является админом или создателем.
    Если нет — отправляет ответ и возвращает False.
    """
    user = await client.get_chat_member(message.chat.id, message.from_user.id)
    message.from_user.restrictions
    if not user.privileges:
        msg = await message.reply(
            f"Вы не являетесь администратором или основателем! {message.from_user.status.value}"
        )
        await asyncio.sleep(3.0)
        await client.delete_messages(message.chat.id, [msg.id, message.id])

        return False
    return True


async def check_is_admin_callback(
    client: Client, callback_query: CallbackQuery
) -> bool:
    """
    Проверяет, что пользователь, нажавший кнопку, является админом или создателем.
    Если нет — отправляет ответ и возвращает False.
    """
    chat_id = callback_query.message.chat.id
    chat_member = await client.get_chat_member(chat_id, callback_query.from_user.id)
    if chat_member.status.value not in ["administrator", "owner"]:
        await callback_query.answer(
            "Вы не являетесь администратором или основателем!", show_alert=True
        )
        return False
    return True



>>>>>>> a53e11fce995d431be9bea2ffb0b994581498aac
def ban_button(user_id: int, msg_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton(
                    text="🚫 Забанить",
                    callback_data=f"ban_user_{user_id}_{msg_id}",
                ),
                InlineKeyboardButton(
                    text="🗑 Просто удалить",
                    callback_data="delete",
                ),
                InlineKeyboardButton(
                    text="❌ Отмена",
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
    if not await check_is_admin(client, message):
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



@bot.on_message(filters.text & ~filters.channel & ~filters.bot)
async def main(client: Client, message: Message) -> None:
    """
    Обрабатывает входящие текстовые сообщения, проверяет наличие запрещенных слов.
    Если слова найдены, удаляет сообщение и логирует.
    """
    try:
<<<<<<< HEAD
        # Проверяем, ожидается ли слово от этого пользователя
        if waiting_for_word.get(message.from_user.id):
            # Добавляем слово в файл
=======
        
        if waiting_for_word[message.from_user.id]:
            
>>>>>>> a53e11fce995d431be9bea2ffb0b994581498aac
            word = message.text.strip()
            chat_id = message.chat.id

            
            success = db.add_chat_badword(chat_id, word, message.from_user.id)

            
            waiting_for_word[message.from_user.id] = False
            global filter_settings_markup
            if success:
                await message.reply(
                    f"✅ Слово **{word}** добавлено в список запрещенных для этого чата!\n\n",
                    reply_markup=filter_settings_markup,
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
            f"Processing message from {message.chat.id} {f"- {message.chat.username}" if message.chat.username else ""} - {message.from_user.id}: {" ".join(text.splitlines())}"
        )

        def ensure_chat_exists(chat_id: int, chat_title: str = None):
            db.cursor.execute("SELECT chat_id FROM chats WHERE chat_id = ?", (chat_id,))
            if not db.cursor.fetchone():
                db.cursor.execute(
                    "INSERT INTO chats (chat_id, title) VALUES (?, ?)",
                    (chat_id, chat_title or "Неизвестный чат"),
                )
                db.connection.commit()
        
        if db.is_user_banned(message.from_user.id):
            await message.delete()
        
        ensure_chat_exists(message.chat.id, message.chat.title)
        
        
        is_spam = search_keywords(text, message.chat.id)

        
        db.add_user(
            user_id=message.from_user.id,
            first_name=message.from_user.first_name,
            username=message.from_user.username if message.from_user.username else None,
        )
        db.add_message(message.chat.id, message.from_user.id, highlight_banned_words(message.text, message.chat.id), is_spam)
        if is_spam:
            is_user_valid = await check_user(message.from_user.id if message.from_user.id != 5957115070 else None)

            # Пропускаем сообщения от доверенных пользователей
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
                    reply_markup=ban_button(message.from_user.id, message.id),
                )
            db.add_spam_warning(message.from_user.id, message.chat.id, message.text)

            db.update_stats(message.chat.id, deleted=True)

    except Exception as e:
        logger.exception(f"Error processing message: {e}")



if __name__ == "__main__":
    start_time = time.time()  
    bot.run()  

    
    total_time = round(time.time() - start_time, 2)
    logger.info(
        f"Total uptime {total_time if total_time < 3600 else int(total_time/60)} seconds. Bot stopped."
    )
