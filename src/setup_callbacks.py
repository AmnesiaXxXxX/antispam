from pyrogram import filters
from pyrogram.handlers.callback_query_handler import CallbackQueryHandler

from src.functions.callbacks import (
    add_badword_callback,
    autoclean_settings_callback,
    back_to_main_callback,
    ban_user_callback,
    cancel_add_word_callback,
    cancel_callback,
    delete_callback,
    delete_word_handler,
    exit_callback,
    filter_settings_callback,
    list_badwords_callback,
    remove_badword_handler,
    settings_callback,
    stats_callback,
    stats_graph_callback,
    toggle_autoclean_callback,
    thank_me,
)
from src.setup_bot import bot
from src.filters import is_admin


def setup_callbacks():
    """
    Sets up callback query handlers for the bot. Registers handlers for various
    callback queries including removing bad words, deleting words, banning users,
    and general callback queries.
    """

    bot.add_handler(
        CallbackQueryHandler(
            remove_badword_handler, filters.regex(r"^remove_badword$") & is_admin
        )
    )
    bot.add_handler(
        CallbackQueryHandler(
            delete_word_handler, filters.regex(r"^del_word_$") & is_admin
        )
    )

    bot.add_handler(
        CallbackQueryHandler(
            ban_user_callback, filters.regex(r"^ban_user_(\d+)_(\d+)$") & is_admin
        )
    )

    bot.add_handler(
        CallbackQueryHandler(
            add_badword_callback, filters.regex(r"add_badword") & is_admin
        )
    )
    bot.add_handler(
        CallbackQueryHandler(
            autoclean_settings_callback,
            filters.regex(r"^autoclean_settings") & is_admin,
        )
    )
    bot.add_handler(
        CallbackQueryHandler(back_to_main_callback, filters.regex(r"^back_to_main$"))
    )
    bot.add_handler(CallbackQueryHandler(stats_callback, filters.regex(r"^stats$")))
    bot.add_handler(
        CallbackQueryHandler(stats_graph_callback, filters.regex(r"^stats_graph$"))
    )
    bot.add_handler(
        CallbackQueryHandler(
            cancel_add_word_callback, filters.regex(r"^cancel_add_word") & is_admin
        )
    )
    bot.add_handler(CallbackQueryHandler(cancel_callback, filters.regex(r"^cancel$")))
    bot.add_handler(
        CallbackQueryHandler(delete_callback, filters.regex(r"^delete$") & is_admin)
    )
    bot.add_handler(CallbackQueryHandler(exit_callback, filters.regex(r"^exit$")))
    bot.add_handler(CallbackQueryHandler(thank_me, filters.regex(r"^thank_me$")))
    bot.add_handler(
        CallbackQueryHandler(
            filter_settings_callback, filters.regex(r"^filter_settings")
        )
    )
    bot.add_handler(
        CallbackQueryHandler(
            list_badwords_callback, filters.regex(r"^list_badwords$") & is_admin
        )
    )
    bot.add_handler(
        CallbackQueryHandler(settings_callback, filters.regex(r"^settings$"))
    )
    bot.add_handler(
        CallbackQueryHandler(
            toggle_autoclean_callback, filters.regex(r"^toggle_autoclean") & is_admin
        )
    )
