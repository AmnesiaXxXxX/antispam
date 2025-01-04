from pyrogram import Client, filters
from pyrogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
import logging
import asyncio
from typing import List
import unidecode
from ..utils.filters import get_keywords
from ..utils.ban import ban_user, check_user
from ..utils.text_loader import load_text

@Client.on_message(filters.command(["start"]))
async def start(client: Client, message: Message):
    await message.reply(load_text("start"))

@Client.on_message(filters.command(["info"]))
async def info(client: Client, message: Message):
    await message.reply(load_text("info"))

async def start_command(client: Client, message: Message):
    await message.reply(
        """
<b>👋 Всем привет!</b> Я <b>антиспам-бот</b>. 🛡️
        
📝 <b>Контакты</b> 
Хотите написать оскорбления админу, используйте команду <b>/contact</b>. 📬

💡 <b>Есть идеи для улучшения?</b> 
Одмены, не стесняйтесь писать через тот же <b>/contact</b>. Мы ждём ваши предложения! ✨

ℹ️ <b>Интересно, как я работаю?</b> 
Воспользуйтесь командой <b>/info</b> для подробностей. 🔍
        """
    )

@Client.on_message(filters.command(["add_badword"]))
async def add_badword(client, message: Message):
    word = " ".join(message.text.split(" ")[1:])
    with open("bad_words.txt", "a", encoding="utf-8") as f:
        f.write(f"\n{unidecode.unidecode(word.lower())}")
    keywords = get_keywords()
    await message.reply(
        f"Добавлено слово: {word}\nТекущий список запрещенных слов:\n{', '.join(keywords)}"
    )

@Client.on_message(filters.command(["ban"]) & filters.user(5957115070))
async def ban(client: Client, message: Message):
    if message.reply_to_message:
        user_id = message.reply_to_message.from_user.id
    elif message.text.split(" ")[1:]:
        user_id = int(message.text.split(" ")[1])
    else:
        await message.reply("Укажите ID пользователя после команды.")
        return
    if not user_id:
        return
    await ban_user(client, user_id)
    await message.reply(f"Пользователь `{user_id}` забанен.")

def register_commands(bot: Client):
    """Регистрация всех команд бота"""
    commands = [
        start_command,
        add_badword,
        ban,
        # Добавьте остальные команды
    ]
    
    for command in commands:
        bot.on_message(filters.command([command.__name__.replace("_command", "")])(command))
