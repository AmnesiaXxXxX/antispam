import re
import unidecode
from typing import List

def get_keywords() -> List[str]:
    """Читает список запрещенных слов из файла."""
    try:
        with open("bad_words.txt", "r", encoding="utf-8") as f:
            keywords = unidecode.unidecode(f.read().lower().replace(" ", "")).splitlines()
        return keywords
    except Exception:
        return []

def search_keywords(text: str) -> bool:
    """Ищет запрещенные слова в тексте."""
    text = unidecode.unidecode(text)
    try:
        keywords = get_keywords() or ["слово"]
        pattern = r"(" + "|".join(keywords) + r")"
        found_keywords = [match.group() for match in re.finditer(pattern, text, re.IGNORECASE)]
        return len(found_keywords) > 4
    except Exception:
        return False
