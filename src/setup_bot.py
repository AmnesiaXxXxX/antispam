from pyrogram.client import Client

from src.constants import api_hash, api_id, bot_token

def setup_bot():

    return Client(
        "bot",
        api_id=api_id,
        api_hash=api_hash,
        bot_token=bot_token,
    )


bot = setup_bot()