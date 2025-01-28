import os
import logging
import datetime
from logging.handlers import RotatingFileHandler

def setup_logger():
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)

    log_filename = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d.log")
    log_path = os.path.join(log_dir, log_filename)

    logger = logging.getLogger("antispam")
    logger.setLevel(logging.INFO)

    file_handler = logging.FileHandler(log_path)
    file_handler.setLevel(logging.INFO)

    formatter = logging.Formatter(
        "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )
    file_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    return logger

def setup_flask_logger(log_file):
    flask_logger = logging.getLogger('flask_logger')  # Имя нового логгера
    flask_logger.setLevel(logging.DEBUG)  # Уровень логирования

    # Обработчик для записи логов в файл
    handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5)  # Ротация файлов
    handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
    
    flask_logger.addHandler(handler)
    return flask_logger

logger = setup_logger()
