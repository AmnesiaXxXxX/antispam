import time

# from src.callback.server import app
from src.setup_bot import bot
from src.utils.logger_config import logger


if __name__ == "__main__":
    start_time = time.time()

    from src.setup_callbacks import setup_callbacks
    from src.setup_handlers import setup_handlers

    setup_callbacks()
    setup_handlers()
    bot.run()
    # app.run(host="localhost", port=3005)
    total_time = round(time.time() - start_time, 2)
    logger.info(
        f"Total uptime {total_time if total_time < 3600 else int(total_time / 60)} seconds. Bot stopped."
    )
