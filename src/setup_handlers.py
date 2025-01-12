from pyrogram import filters
from pyrogram.handlers.message_handler import MessageHandler

from src.functions.functions import (
    add_autos,
    add_badword,
    get_autos,
    menu_command,
    on_new_member,
    remove_autos,
    set_threshold,
    start,
    invert,
    gen_regex,
    list_command,
    check_command,
    main,
)
from app import bot


def setup_handlers():
    bot.add_handler(MessageHandler(menu_command, filters.text & filters.command(["menu"])))
    bot.add_handler(MessageHandler(add_badword, filters.text & filters.command(["add_badword"])))
    bot.add_handler(MessageHandler(on_new_member, filters.new_chat_members))
    bot.add_handler(MessageHandler(set_threshold, filters.text & filters.command("set_threshold")))
    bot.add_handler(MessageHandler(start, filters.text & filters.command(["start"])))
    bot.add_handler(MessageHandler(invert, filters.text & filters.command(["invert"])))
    bot.add_handler(MessageHandler(gen_regex, filters.text & filters.command(["gen_regex"])))
    bot.add_handler(MessageHandler(list_command, filters.text & filters.command(["list"])))
    bot.add_handler(MessageHandler(check_command, filters.text & filters.command(["check"])))
    bot.add_handler(MessageHandler(get_autos, filters.text & filters.command(["get_autos"])))
    bot.add_handler(MessageHandler(add_autos, filters.text & filters.command(["autoclean"])))
    bot.add_handler(MessageHandler(remove_autos, filters.text & filters.command(["remove_autoclean"])))
    bot.add_handler(MessageHandler(main, filters.text & ~filters.channel & ~filters.bot)
)
