import json
import asyncio
import datetime
import os
import re
import time
from functools import lru_cache
from typing import List, Optional
from logger_config import logger
import pyrogram.errors
from database import Database
import pyrogram
import aiohttp
import unidecode
from dotenv import load_dotenv
from pyrogram import Client, filters  # type: ignore
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
    User,
)

from collections import defaultdict

# Загрузка переменных окружения из .env файла
load_dotenv()

db = Database("antispam.db")

# Токены и ключи для работы с API
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

START_MESSAGE = """# 🤖 Великий Фильтр - Умный инструмент для защиты чатов

Великий Фильтр - это современное решение для предотвращения спама и управления чатами. С помощью этого бота вы сможете обеспечить чистоту и безопасность вашего сообщества, не прибегая к ручной модерации каждый раз.


## 📋 Основные возможности

### 🛡️ Антиспам - функции
- **Фильтрация спама и ключевых слов**:  
  Мощные алгоритмы автоматически блокируют нежелательные сообщения и ключевые слова, упрощая общение участников.  
- **Защита от нежелательных символов**:  
  Определяет и блокирует запрещенные символы, включая скрытые комбинации, часто используемые для обхода стандартных фильтров.  
- **Проверка новых участников**:  
  Анализ профилей новых пользователей при вступлении помогает выявить и ограничить доступ подозрительным аккаунтам.

### 👮 Модерация
- **Удаление и блокировка**:  
  Позволяет автоматически или вручную удалять сообщения и блокировать нарушителей. Это обеспечивает соблюдение правил чата.  
- **Пересылка подозрительных сообщений**:  
  Подозрительные сообщения отправляются модераторам на проверку, что помогает снизить вероятность ложных блокировок.

### ⚙️ Настройка параметров
- **Удобный интерфейс**:  
  Бот предоставляет интуитивно понятные кнопки и меню для управления его функциями.  
- **Регулировка чувствительности фильтров**:  
  Подстройте уровень фильтрации под размер и специфику вашего сообщества.

### 📊 Аналитика и отчёты
- **Отслеживание активности**:  
  Бот собирает данные об активности участников и нарушениях, создавая подробные отчёты для анализа.  
- **Динамическая статистика**:  
  Анализ данных помогает выявить проблемные зоны и оптимизировать управление чатом.

### 🗄️ Надёжное хранение данных
- **Использование SQLite**:  
  Легковесная база данных надёжно сохраняет настройки и логи, обеспечивая долгосрочное хранение данных.

### 🔒 Конфиденциальность и безопасность
- **Администрирование с защитой**:  
  Только администраторы имеют доступ к управлению ботом, а пользовательские данные защищены на всех этапах обработки. Это гарантирует высокий уровень безопасности.

### 🛠️ Технические особенности
- **Асинхронная работа**:  
  Бот обрабатывает множество запросов одновременно, что обеспечивает высокую производительность даже в крупных сообществах.  
- **Интеграция с API и кэширование**:  
  Использует кэширование для ускорения работы и поддерживает взаимодействие с внешними сервисами через API.


Великий Фильтр - это идеальный выбор для модерирования чатов любых масштабов. Его возможности и гибкость настройки позволяют адаптировать работу бота под потребности вашего сообщества, обеспечивая комфорт и безопасность для всех участников.


"""
WORDS_PER_PAGE = 5  # Количество слов на странице


# Инициализация бота с использованием токенов
bot = Client(
    "bot",
    api_id=api_id,
    api_hash=api_hash,
    bot_token=bot_token,
)

# Добавляем после импортов
SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD", "3"))  # Порог по умолчанию
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

    # Получаем параметр страницы из callback_data
    page = 0
    if "_" in callback_query.data:
        page = int(callback_query.data.split("_")[1])

    chat_id = callback_query.message.chat.id

    # Получаем список слов для данного чата
    words = db.get_chat_badwords(chat_id)
    total_pages = (len(words) - 1) // WORDS_PER_PAGE

    # Формируем кнопки для текущей страницы
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

    # Добавляем кнопки навигации
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

    # Добавляем кнопку возврата
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

        # Удаляем слово из базы данных
        db.cursor.execute(
            "DELETE FROM chat_badwords WHERE chat_id = ? AND word = ?", (chat_id, word)
        )
        db.connection.commit()

        await callback_query.answer(f"Слово '{word}' удалено!")
        # Возвращаемся к списку слов
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

        # Проверяем, является ли пользователь администратором
        if not await check_is_admin_callback(client, callback_query):
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
        # Получаем статистику
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
        # Проверка прав администратора
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
        # Проверяем, включена ли автомодерация для этого чата
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


# Функция для проверки пользователя через FunStat API
async def check_user(user_id: int) -> bool | Optional[str]:
    """
    Проверяет пользователя через FunStat API и сохраняет результаты в БД.
    """
    if not user_id:
        raise ValueError()

    # Сначала проверяем, есть ли пользователь уже в БД
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
                    # Сохраняем данные о проверенном пользователе
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


# Функция для чтения списка запрещенных слов из файла
def get_keywords(chat_id: int = None) -> List[str]:
    """
    Читает список запрещенных слов.
    Если указан chat_id, добавляет к общему списку слова конкретного чата.
    """
    try:
        # Получаем общий список слов
        with open("bad_words.txt", "r", encoding="utf-8") as f:
            keywords = unidecode.unidecode(
                f.read().lower().replace(" ", "")
            ).splitlines()

        # Если указан chat_id, добавляем слова конкретного чата
        if chat_id:
            chat_keywords = db.get_chat_badwords(chat_id)
            keywords.extend(chat_keywords)

        # Удаляем дубликаты и пустые строки
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
    # Проверяем, был ли добавлен именно бот
    for new_member in message.new_chat_members:
        if new_member.is_self:
            # Отправляем сообщение, когда бот был добавлен в чат
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


@lru_cache(maxsize=128)
def get_special_patterns() -> List[str]:
    """Возвращает список скомпилированных регулярных выражений для специальных символов."""
    return [
        r"[\u0500-\u052F]",  # Расширенная кириллица
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
        if not await check_is_admin(client, message):
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
        await message.reply(
            f"Текущий порог: {SPAM_THRESHOLD}" f"Использование /set_threshold [Число]"
        )
    except Exception as e:
        logger.error(f"Ошибка при установке порога: {str(e)}")
        await message.reply(f"Ошибка при установке порога: {str(e)}")


# Команда /start
@bot.on_message(filters.text & filters.command(["start"]))
async def start(client: Client, message: Message):
    await message.reply(START_MESSAGE)


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


# Функция для создания кнопок с баном и отменой
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


# Основная логика для обработки текстовых сообщений
@bot.on_message(filters.text & ~filters.channel & ~filters.bot)
async def main(client: Client, message: Message) -> None:
    """
    Обрабатывает входящие текстовые сообщения, проверяет наличие запрещенных слов.
    Если слова найдены, удаляет сообщение и логирует.
    """
    try:
        # Проверяем, ожидается ли слово от этого пользователя
        if waiting_for_word[message.from_user.id]:
            # Добавляем слово в файл
            word = message.text.strip()
            chat_id = message.chat.id

            # Добавляем слово в базу данных для конкретного чата
            success = db.add_chat_badword(chat_id, word, message.from_user.id)

            # Сбрасываем состояние ожидания
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

        # Читаем список автомодерации
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

        # Перед сохранением сообщения добавляем:
        ensure_chat_exists(message.chat.id, message.chat.title)
        # Сохраняем сообщение в БД
        # Проверяем наличие спама
        is_spam = search_keywords(text, message.chat.id)

        # Сохраняем сообщение в БД
        db.add_user(
            user_id=message.from_user.id,
            first_name=message.from_user.first_name,
            username=message.from_user.username if message.from_user.username else None,
        )
        db.add_message(message.chat.id, message.from_user.id, text, is_spam)
        if is_spam:
            # is_user_valid = await check_user(message.from_user.id)

            # Пропускаем сообщения от доверенных пользователей
            # if is_user_valid == "False" and message.from_user.id != 5957115070:
            #     return

            await message.forward("amnesiawho1")

            # Проверяем режим автомодерации для чата
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


# Запуск бота
if __name__ == "__main__":
    start_time = time.time()  # Засекаем время старта бота
    bot.run()  # Запускаем бота

    # Логируем время работы бота
    total_time = round(time.time() - start_time, 2)
    logger.info(
        f"Total uptime {total_time if total_time < 3600 else int(total_time/60)} seconds. Bot stopped."
    )
