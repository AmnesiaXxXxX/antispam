from typing import Optional
from uuid import uuid4

from pyrogram import errors
from pyrogram.client import Client
from pyrogram.errors import UserNotParticipant
from pyrogram.types import (
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from yookassa import Configuration, Payment

from src.constants import (
    WORDS_PER_PAGE,
    account_id,
    secret_key,
    waiting_for_payment,
    waiting_for_word,
)
from src.database import db
from src.markups.markups import (
    get_filter_settings_button,
    get_main_menu,
    get_settings_button,
)
from src.utils.logger_config import logger


def safe_get_callback_data(callback_query: CallbackQuery) -> Optional[str]:
    """
    Безопасно получает данные из callback_query, возвращает None, если данные отсутствуют.
    """
    return str(callback_query.data) if callback_query and callback_query.data else None


async def remove_badword_handler(client: Client, callback_query: CallbackQuery) -> None:
    """
    Обработчик для удаления запрещённого слова.
    Отображает список слов и даёт возможность перейти по страницам.
    """
    callback_data = safe_get_callback_data(callback_query)
    if not callback_data:
        await callback_query.answer("Нет данных для обработки.", show_alert=True)
        return

    # Пытаемся получить номер страницы
    page = 0
    try:
        if "_" in callback_data:
            _, page_str = callback_data.split("_", 1)
            page = int(page_str)
    except ValueError:
        page = 0  # Если что-то пошло не так при конвертации, начинаем с 0

    chat_id = callback_query.message.chat.id
    words = db.get_chat_badwords(chat_id)

    # Если слов нет, сразу возвращаемся
    if not words:
        await callback_query.message.edit_text(
            "Список запрещённых слов пуст.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("◀️ Назад", callback_data="filter_settings")]]
            ),
        )
        return

    total_pages = max((len(words) - 1) // WORDS_PER_PAGE, 0)

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

    # Кнопки пагинации
    nav_buttons = []
    if page > 0:
        nav_buttons.append(
            InlineKeyboardButton("⬅️", callback_data=f"remove_badword_{page - 1}")
        )
    if page < total_pages:
        nav_buttons.append(
            InlineKeyboardButton("➡️", callback_data=f"remove_badword_{page + 1}")
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


async def delete_word_handler(client: Client, callback_query: CallbackQuery) -> None:
    """
    Функция удаления выбранного слова из базы.
    """
    callback_data = safe_get_callback_data(callback_query)
    if not callback_data:
        await callback_query.answer("Нет данных для удаления.", show_alert=True)
        return

    try:
        # Пример строки: "del_word_{chat_id}_{word}"
        _, chat_id_str, word = callback_data.split("_", 2)
        chat_id = int(chat_id_str)

        db.cursor.execute(
            "DELETE FROM chat_badwords WHERE chat_id = ? AND word = ?", (chat_id, word)
        )
        db.connection.commit()

        await callback_query.answer(f"Слово '{word}' удалено!")
        await remove_badword_handler(client, callback_query)

    except ValueError:
        logger.error("Ошибка при парсинге данных для удаления слова.")
        await callback_query.answer("Ошибка при удалении слова", show_alert=True)
    except Exception as e:
        logger.error(f"Error deleting word: {e}")
        await callback_query.answer("Ошибка при удалении слова", show_alert=True)


async def ban_user_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Обработчик бана пользователя. Проверяем, не является ли пользователь админом/владельцем,
    не пытаемся ли забанить бота или самого себя.
    """
    callback_data = safe_get_callback_data(callback_query)
    if not callback_data:
        await callback_query.answer("Нет данных для бана.", show_alert=True)
        return

    answer = "OK"
    try:
        data = callback_data.lower().replace("ban_user_", "").split("_")
        if len(data) < 2:
            raise ValueError("Недостаточно данных для бана пользователя.")

        user_id = int(data[0])
        msg_id = int(data[1])
        chat_id = callback_query.message.chat.id

        if user_id == client.me.id:
            raise errors.ChatAdminRequired("Невозможно забанить бота.")
        if user_id == callback_query.from_user.id:
            raise errors.ChatAdminRequired("Нельзя забанить самого себя.")

        target = await client.get_chat_member(chat_id, user_id)
        if target.status in ["administrator", "owner"]:
            raise errors.ChatAdminRequired(
                "Пользователь является администратором/владельцем."
            )

        await client.ban_chat_member(chat_id, user_id)
        db.update_stats(chat_id, banned=True)

        await client.delete_messages(chat_id, [msg_id, callback_query.message.id])
        answer = "Пользователь забанен!"
    except errors.ChatAdminRequired as e:
        answer = str(e)
    except UserNotParticipant as e:
        answer = str(e)
    except ValueError as e:
        logger.error(f"Ошибка при обработке данных бана: {e}")
        answer = str(e)
    except Exception as e:
        logger.error(f"Error banning user: {e}")
        answer = "Произошла ошибка при бане пользователя."
    finally:
        await callback_query.answer(answer, show_alert=True)



async def stats_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Показывает базовую статистику чата.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "stats":
        chat_id = callback_query.message.chat.id
        stats = db.get_stats(chat_id)
        if stats and len(stats) >= 2:
            await callback_query.message.edit_text(
                f"📊 Статистика чата:\n\n"
                f"Всего сообщений обработано: {stats[0]}\n"
                f"Из них удалено сообщений: {stats[1]}\n",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "Показать статистику графиком",
                                callback_data="stats_graph",
                            ),
                        ],
                        [
                            InlineKeyboardButton(
                                "◀️ Назад", callback_data="back_to_main"
                            ),
                        ],
                    ]
                ),
            )
        else:
            await callback_query.message.edit_text(
                "Не удалось получить статистику.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")]]
                ),
            )


async def stats_graph_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Обработчик для кнопки вывода графика статистики.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "stats_graph":
        chat_id = callback_query.message.chat.id
        result = db.get_stats_graph(chat_id)
        if isinstance(result, str):
            await callback_query.message.reply_photo(
                result,
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton("❌ Отмена", callback_data="cancel"),
                        ]
                    ]
                ),
            )
        else:
            await callback_query.answer(
                "Не удалось сформировать график.", show_alert=True
            )


async def exit_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Завершает операцию и удаляет сообщение, а также исходное сообщение при наличии.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "exit":
        message = callback_query.message
        if message.reply_to_message:
            await message.reply_to_message.delete()
        await message.delete()


async def list_badwords_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Показывает список всех запрещённых слов в текущем чате.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "list_badwords":
        chat_id = callback_query.message.chat.id
        words = db.get_chat_badwords(chat_id)
        if not words:
            await callback_query.message.edit_text(
                "Список запрещённых слов пуст.",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("◀️ Назад", callback_data="filter_settings")]]
                ),
            )
        else:
            text = "📋 Список запрещённых слов:\n\n" + "\n".join(words)
            await callback_query.message.edit_text(
                text,
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("◀️ Назад", callback_data="filter_settings")]]
                ),
            )


async def cancel_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Универсальная функция для отмены действия и удаления сообщения.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "cancel":
        await callback_query.message.delete()


async def delete_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Удаляет сообщение, к которому привязана кнопка, и сообщение-ответ.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "delete":
        try:
            message = callback_query.message
            messages_to_delete = []
            if message.reply_to_message:
                messages_to_delete.append(message.reply_to_message.id)
            messages_to_delete.append(message.id)

            if messages_to_delete:
                await client.delete_messages(message.chat.id, messages_to_delete)
                db.update_stats(message.chat.id, deleted=True)
                logger.info(
                    f"Messages {messages_to_delete} deleted in chat {message.chat.id}"
                )
        except Exception as e:
            logger.error(f"Error deleting messages: {e}")


async def settings_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Общие настройки бота.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "settings":
        await callback_query.message.edit_text(
            "⚙️ Настройки бота:", reply_markup=get_settings_button()
        )


async def back_to_main_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Возврат в главное меню.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "back_to_main":
        await callback_query.message.edit_text(
            "🔧 Главное меню настроек бота:", reply_markup=get_main_menu()
        )


async def autoclean_settings_callback(
    client: Client, callback_query: CallbackQuery
) -> None:
    """
    Отображает статус автомодерации и кнопку переключения.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "autoclean_settings":
        chat_id = str(callback_query.message.chat.id)
        try:
            with open("autos.txt", "r", encoding="utf-8") as f:
                autos = f.read().splitlines()
        except FileNotFoundError:
            autos = []

        is_auto = chat_id in autos
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
            f"Текущий статус: **{status}**\n\n"
            f"При включенной автомодерации подозрительные сообщения "
            f"будут удаляться автоматически, без подтверждения администратора.",
            reply_markup=autoclean_markup,
        )


async def toggle_autoclean_callback(
    client: Client, callback_query: CallbackQuery
) -> None:
    """
    Переключение статуса автомодерации: включает или выключает функцию для текущего чата.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "toggle_autoclean":
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
            f"Текущий статус: **{status}**\n\n"
            f"При включенной автомодерации подозрительные сообщения "
            f"будут удаляться автоматически, без подтверждения администратора.",
            reply_markup=autoclean_markup,
        )

        await callback_query.answer()


async def filter_settings_callback(
    client: Client, callback_query: CallbackQuery
) -> None:
    """
    Настройки фильтрации (запрещённые слова, отображение списка и т.п.).
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "filter_settings":
        await callback_query.message.edit_text(
            "⚙️ Настройки фильтрации:", reply_markup=get_filter_settings_button()
        )


async def add_badword_callback(client: Client, callback_query: CallbackQuery) -> None:
    """
    Переводит бота в режим ожидания ввода нового запрещённого слова.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "add_badword":
        waiting_for_word[callback_query.from_user.id] = True
        await callback_query.message.edit_text(
            "📝 Отправьте слово, которое хотите добавить в список запрещённых.\n"
            "Для отмены нажмите кнопку ниже.",
            reply_markup=InlineKeyboardMarkup(
                [[InlineKeyboardButton("❌ Отмена", callback_data="cancel_add_word")]]
            ),
        )


async def cancel_add_word_callback(
    client: Client, callback_query: CallbackQuery
) -> None:
    """
    Отмена добавления нового запрещённого слова.
    """
    callback_data = safe_get_callback_data(callback_query)
    if callback_data == "cancel_add_word":
        waiting_for_word[callback_query.from_user.id] = False
        await callback_query.message.edit_text(
            "⚙️ Настройки фильтрации:", reply_markup=get_filter_settings_button()
        )


async def thank_me(client: Client, callback_query: CallbackQuery) -> None:
    """
    Отправляет благодарность разработчику (или любому указанному пользователю).
    """
    try:
        await client.send_message(
            "amnesiawho1", f"{callback_query.from_user.first_name} сказал(а) спасибо!"
        )
        await callback_query.answer("Чмок", cache_time=1000)
    except Exception as e:
        logger.error(f"Ошибка при отправке благодарности: {e}")
        await callback_query.answer("Ошибка при отправке сообщения.")
