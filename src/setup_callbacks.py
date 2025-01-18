from pyrogram import filters
from pyrogram.handlers.callback_query_handler import CallbackQueryHandler

from src.functions.callbacks import (
    remove_badword_handler,
    delete_word_handler,
    ban_user_callback,
    callback_query,
)
from src.setup_bot import bot


def setup_callbacks():
    """
    Sets up callback query handlers for the bot. Registers handlers for various
    callback queries including removing bad words, deleting words, banning users,
    and general callback queries.
    """

    bot.add_handler(
        CallbackQueryHandler(remove_badword_handler, filters.regex(r"^remove_badword"))
    )
    bot.add_handler(
        CallbackQueryHandler(delete_word_handler, filters.regex(r"^del_word_"))
    )

    bot.add_handler(
        CallbackQueryHandler(ban_user_callback, filters.regex(r"ban_user_(\d+)_(\d+)"))
    )

    bot.add_handler(
        CallbackQueryHandler(
            callback_query,
        )
    )
