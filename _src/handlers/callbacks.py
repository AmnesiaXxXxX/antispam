from pyrogram import Client, filters
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup


async def delete_callback(client: Client, callback_query: CallbackQuery):
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


async def cancel_callback(client: Client, callback_query: CallbackQuery):
    chat_id = callback_query.message.chat.id
    chat_member = await client.get_chat_member(chat_id, callback_query.from_user.id)
    if chat_member.status.value in ["administrator", "owner"]:
        await callback_query.message.delete()
    else:
        await callback_query.answer(
            "Вы не являетесь администратором или основателем!", show_alert=True
        )


async def ban_callback(client: Client, callback_query: CallbackQuery):
    try:
        callback_query.data = callback_query.data.replace("ban_user_", "")
        msg_id = int(callback_query.data.split("_")[1])
        user_id = int(callback_query.data.split("_")[0])
        chat_id = callback_query.message.chat.id
        chat_member = await client.get_chat_member(chat_id, callback_query.from_user.id)
        target = await client.get_chat_member(chat_id, user_id)

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


def register_callbacks(bot: Client):
    """Регистрация всех callback-обработчиков"""
    bot.on_callback_query(filters.regex(r"delete"))(delete_callback)
    bot.on_callback_query(filters.regex(r"cancel"))(cancel_callback)
    bot.on_callback_query(filters.regex(r"ban_user_(\d+)_(\d+)"))(ban_callback)


def get_keyboard(user_id: int, msg_id: int) -> InlineKeyboardMarkup:
    """Создает клавиатуру с кнопками действий."""
    return InlineKeyboardMarkup(
        [[
            InlineKeyboardButton(text="Забанить", callback_data=f"ban_user_{user_id}_{msg_id}"),
            InlineKeyboardButton(text="Просто удалить", callback_data="delete"),
            InlineKeyboardButton(text="Галя, отмена", callback_data="cancel"),
        ]]
    )
