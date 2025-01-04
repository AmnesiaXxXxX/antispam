import logging
import os
import datetime
from logging.handlers import RotatingFileHandler

def setup_logger() -> logging.Logger:
    """Настройка и инициализация логгера"""
    
    # Создание директории для логов
    log_dir = "logs"
    os.makedirs(log_dir, exist_ok=True)
    
    # Настройка файла лога
    log_path = os.path.join(
        log_dir, 
        datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d.log")
    )
    
    # Инициализация логгера
    logger = logging.getLogger()
    logger.setLevel(logging.INFO)
    
    # Настройка ротации файлов
    handler = RotatingFileHandler(
        log_path,
        maxBytes=10**6,  # 1 МБ
        backupCount=5
    )
    handler.setFormatter(
        logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    )
    
    logger.addHandler(handler)
    return logger
