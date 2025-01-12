import time
from src.utils.logger_config import logger
from src.setup_bot import bot

if __name__ == "__main__":
    from src.setup_callbacks import setup_callbacks
    from src.setup_handlers import setup_handlers

    start_time = time.time()

    setup_callbacks()
    setup_handlers()
    bot.run()

    total_time = round(time.time() - start_time, 2)
    logger.info(
        f"Total uptime {total_time if total_time < 3600 else int(total_time / 60)} seconds. Bot stopped."
    )
