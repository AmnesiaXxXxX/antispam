import os
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()
WORDS_PER_PAGE = 5
SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD", "3"))
token = os.getenv("TOKEN") or exit("TOKEN is not set")
bot_token = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN is not set")
api_id = os.getenv("API_ID") or exit("API_ID is not set")
api_hash = os.getenv("API_HASH") or exit("API_HASH is not set")
waiting_for_word = defaultdict(bool)

START_MESSAGE = """

**Великий Фильтр** – это мощный бот для защиты вашего чата от спама и нарушений.

### Возможности:
- **Фильтрация спама и ключевых слов**: Автоматически блокирует нежелательные сообщения и символы.
- **Проверка новых участников**: Анализ профилей для выявления подозрительных аккаунтов.
- **Автоблокировка**: Удаление нарушений и блокировка пользователей.
- **Удобный интерфейс**: Интуитивные кнопки и гибкие настройки.
- **Статистика и отчёты**: Анализ активности участников для улучшения чата.
- **Безопасность**: Данные пользователей защищены, доступ к управлению только у админов.
- **Высокая производительность**: Асинхронная работа и поддержка API.

**Великий Фильтр** – идеальное решение для комфортного и безопасного общения!
"""
