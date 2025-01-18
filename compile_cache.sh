#!/bin/bash

PROJECT_DIR="/home/bot1/antispam/"
CACHE_DIR="/home/bot1/pycache"

mkdir -p "$CACHE_DIR"
python3 -m compileall -f -q "$PROJECT_DIR"
find "$PROJECT_DIR" -name "*.pyc" -exec mv {} "$CACHE_DIR" \;
find "$PROJECT_DIR" -type d -name "__pycache__" -exec rm -r {} +

echo "Кэш обновлён."
