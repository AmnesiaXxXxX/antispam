from pyrogram.types import InlineKeyboardButton, InlineKeyboardMarkup


def get_main_menu():
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("📊 Статистика", callback_data="stats")],
            [InlineKeyboardButton("⚙️ Настройки", callback_data="settings")],
            [InlineKeyboardButton("❌ Закрыть", callback_data="exit")],
        ]
    )


def get_ban_button(user_id: int, msg_id) -> InlineKeyboardMarkup:
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


def get_filter_settings_button():
    return InlineKeyboardMarkup(
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
                InlineKeyboardButton(
                    "📋 Вывод списка слов", callback_data="list_badwords"
                ),
            ],
        ]
    )
def get_settings_button():
    return InlineKeyboardMarkup(
            [
                [
                    InlineKeyboardButton(
                        "🔍 Настройки фильтрации", callback_data="filter_settings"
                    )
                ],
                # [
                #     InlineKeyboardButton(
                #         " ⚙️ Пресеты фильтров", callback_data="ban_settings"
                #     )
                # ],
                [
                    InlineKeyboardButton(
                        "⏰ Автоочистка", callback_data="autoclean_settings"
                    )
                ],
                [InlineKeyboardButton("◀️ Назад", callback_data="back_to_main")],
            ]
        )
def get_users_ban_pending(from_user_id, id) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🚫 Забанить", callback_data=f"ban_user_{from_user_id}_{id}")],
            [InlineKeyboardButton("❌ Отмена", callback_data="cancel")],
        ]
    )