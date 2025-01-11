from app import get_keywords, get_special_patterns, logger
import unidecode
import re
import os
from dotenv import load_dotenv

load_dotenv()

SPAM_THRESHOLD = float(os.getenv("SPAM_THRESHOLD", "3"))  # Порог по умолчанию


def search_keywords(text: str, chat_id: int = None) -> bool:
    """
    Ищет запрещенные слова и специальные символы в тексте.
    Учитывает слова конкретного чата, если указан chat_id.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Текст должен быть непустой строкой")

    try:
        score = 0
        keywords = get_keywords(chat_id) or ["слово"]

        # Преобразуем текст и ищем ключевые слова
        normalized_text = unidecode.unidecode(text.lower())
        keyword_pattern = r"\b(" + "|".join(map(re.escape, keywords)) + r")\b"
        found_keywords = len(re.findall(keyword_pattern, normalized_text))

        # Добавляем баллы за найденные ключевые слова
        score += found_keywords

        # Проверяем спец-символы
        special_chars_found = 0
        for pattern in get_special_patterns():
            if re.search(pattern, text):
                special_chars_found += 2

        # Добавляем баллы за спец-символы
        score += special_chars_found * 1.5
        return score >= SPAM_THRESHOLD

    except Exception as e:
        logger.error(f"Ошибка при поиске ключевых слов: {str(e)}")
        return False
print(123)
print(search_keywords("кто спᴏсᴏбеʜ приcуʜуть дeʙочᴋᴇ ?)"))
    
