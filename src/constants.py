import os
from collections import defaultdict

from dotenv import load_dotenv

load_dotenv()

WORDS_PER_PAGE = 5
SPAM_THRESHOLD = 2.0
account_id = os.getenv("UMONEYaccount_id")
secret_key = os.getenv("UMONEYsecretKey")

token = os.getenv("TOKEN") or exit("TOKEN is not set")
bot_token = os.getenv("BOT_TOKEN") or exit("BOT_TOKEN is not set")
api_id = os.getenv("API_ID") or exit("API_ID is not set")
api_hash = os.getenv("API_HASH") or exit("API_HASH is not set")
waiting_for_word = defaultdict(bool)
waiting_for_payment = defaultdict(bool)
START_MESSAGE = """

**Великий Фильтр** – это мощный бот для защиты вашего чата от спама и нарушений.

Возможности:
- **Фильтрация спама и ключевых слов**: Автоматически блокирует нежелательные сообщения и символы.
- **Проверка новых участников**: Анализ профилей для выявления подозрительных аккаунтов.
- **Автоблокировка**: Удаление нарушений и блокировка пользователей.
- **Удобный интерфейс**: Интуитивные кнопки и гибкие настройки.
- **Статистика и отчёты**: Анализ активности участников для улучшения чата.
- **Безопасность**: Данные пользователей защищены, доступ к управлению только у админов.
- **Высокая производительность**: Асинхронная работа и поддержка API.

**Великий Фильтр** – идеальное решение для комфортного и безопасного общения!
"""

DONAT_MESSAGE = """
Спасибо, что решили поддержать мой проект! Вы можете отправить пожертвование любым удобным способом:

💳 **Карта РФ:**  
2200700959855247

💰 **Криптовалюта:**  
- **TON:** ||`UQDUEUkYqsnVzTIge3tGXpjdsN2UOhlrDLgcBvS-FQE1gsws`||  
- **USDT (TRC20):** ||`TFRXgou4bU63qNhMj4Bhx8ituWFfTAqbZX`||

Ваша поддержка помогает развивать проект. Спасибо! ❤️
"""
