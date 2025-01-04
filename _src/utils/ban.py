import logging
import asyncio
import datetime
import inspect
import aiohttp
from typing import List, Optional
from pyrogram import Client

async def ban_user(client: Client, user_id: int, channels: List[str] = None):
    if not channels:
        channels = open("channels.txt", "r", encoding="utf-8").read().splitlines()
        
    try:
        for channel in channels:
            try:
                await client.ban_chat_member(channel, user_id)
                logging.info(f"Ban user {user_id} in channel {channel}")
                await asyncio.sleep(0.5)
            except Exception:
                logging.warning(f"Failed to ban user {user_id} in channel {channel}")
        
        with open("banned.txt", "a", encoding="utf-8") as f:
            f.write(f"{user_id}\n")

    except Exception as e:
        logging.exception(f"Error at {ban_user.__name__}: {e}")
        return False

async def check_user(user_id: int, token: str) -> bool | Optional[str]:
    """Проверяет, когда пользователь отправил своё первое сообщение."""
    if not user_id:
        raise ValueError("User ID is required")
    
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                f"http://funstat.org/api/v1/users/{user_id}/stats_min",
                headers={"accept": "application/json", "Authorization": f"Bearer {token}"},
            ) as response:
                result = await response.json()
                
                first_msg_date_str = result.get("first_msg_date")
                if not first_msg_date_str:
                    return False

                first_msg_date = datetime.datetime.strptime(
                    first_msg_date_str, "%Y-%m-%dT%H:%M:%SZ"
                ).replace(tzinfo=datetime.timezone.utc)
                delta = datetime.datetime.now(datetime.timezone.utc) - first_msg_date
                
                return result if delta >= datetime.timedelta(days=60) else False
                
    except Exception as e:
        logging.error(f"Error fetching data: {e}")
        return False
