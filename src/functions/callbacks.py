import pyrogram.errors
from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup

from src.constants import WORDS_PER_PAGE, waiting_for_word
from src.markups.markups import get_filter_settings_button, get_main_menu
from src.functions.functions import check_is_admin_callback
from src.database import db
from src.utils.logger_config import logger


async def remove_badword_handler(client, callback_query):
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


async def delete_word_handler(client, callback_query):
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


async def ban_user_callback(client, callback_query):
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


async def callback_query(client, callback_query):
    data = callback_query.data
    message = callback_query.message
    if data == "stats":
        stats = db.get_stats(callback_query.message.chat.id)
        await callback_query.message.edit_text(
            f"📊 Статистика чата:\n\n"
            f"Всего сообщений обработано: {stats[0]}\n"
            f"Из них удалено сообщений: {stats[1]}\n"
            f"Всего пользователей: {stats[2]}\n"
            f"Заблокировано: {stats[3]}",
            reply_markup=InlineKeyboardMarkup(
                [
                    [
                        InlineKeyboardButton("◀️ Назад", callback_data="back_to_main"),
                    ]
                ]
            ),
        )
    elif data == "exit":
        if message.reply_to_message:
            await message.reply_to_message.delete()
        await message.delete()
    elif data == "list_badwords":
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
            chat_member = (
                await client.get_chat_member(chat_id, callback_query.from_user.id)
                or None
            )
            if not chat_member:
                return

            if chat_member.status.value in ["administrator", "owner"]:
                await callback_query.message.delete()
            else:
                await callback_query.answer(
                    "Вы не являетесь администратором или основателем!", show_alert=True
                )
        except pyrogram.errors.UserNotParticipant:
            await callback_query.answer(
                "Вы не являетесь участником чата", show_alert=True
            )
    elif data == "delete":
        if not await check_is_admin_callback(client, callback_query):
            await callback_query.answer(
                "У вас нет прав для выполнения этого действия!", show_alert=True
            )
            return

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
            f"Текущий статус: **{status}**\n\n"
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
            f"Текущий статус: **{status}**\n\n"
            f"При включенной автомодерации подозрительные сообщения "
            f"будут удаляться автоматически, без подтверждения администратора.",
            reply_markup=autoclean_markup,
        )
        # await callback_query.answer(f"Автомодерация {status}!")
        await callback_query.answer()
    elif data == "filter_settings":
        await callback_query.message.edit_text(
            "⚙️ Настройки фильтрации:", reply_markup=get_filter_settings_button()
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
            "⚙️ Настройки фильтрации:", reply_markup=get_filter_settings_button()
        )
