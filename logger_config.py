import os
import logging
import datetime

# Параметры для логирования
log_dir = "logs"
os.makedirs(log_dir, exist_ok=True)

# Формирование имени файла лога с датой
log_filename = datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%d.log")
log_path = os.path.join(log_dir, log_filename)

# Настройка общего логгера
logger = logging.getLogger('antispam')
logger.setLevel(logging.INFO)

# Создаем обработчик файла
file_handler = logging.FileHandler(log_path)
file_handler.setLevel(logging.INFO)

# Создаем форматтер
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
file_handler.setFormatter(formatter)

# Добавляем обработчик к логгеру
logger.addHandler(file_handler)