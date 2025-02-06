#!/bin/bash

# Проверка компиляции и фикс ошибок стиля

ruff check . --fix --unsafe-fixes 

# Форматирование кода

/home/bot1/.local/bin/black .

sqlite3 my_database.db ".dump" > backup.sql