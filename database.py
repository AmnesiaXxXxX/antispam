import sqlite3
from datetime import datetime

import unidecode
import re


class Database:
    def __init__(self, db_file):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self.create_tables()

    def create_tables(self):
        # Таблица для каналов
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS channels (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            join_date TIMESTAMP,
            settings TEXT,
            is_active BOOLEAN DEFAULT 1
        )""")

        # Таблица для сообщений
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            message_text TEXT,
            timestamp TIMESTAMP,
            is_spam BOOLEAN,
            FOREIGN KEY (chat_id) REFERENCES channels (chat_id)
        )""")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            total_messages INTEGER DEFAULT 0,
            deleted_messages INTEGER DEFAULT 0,
            total_users INTEGER DEFAULT 0,
            banned_users INTEGER DEFAULT 0,
            last_updated TIMESTAMP
        )""")

        # Добавляем таблицу для хранения запрещенных слов по чатам
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_badwords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            word TEXT,
            added_by INTEGER,
            added_at TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES channels (chat_id),
            UNIQUE(chat_id, word)
        )""")
        
        self.connection.commit()

    def update_stats(
        self,
        chat_id: int,
        messages: bool = False,
        deleted: bool = False,
        users: bool = False,
        banned: bool = False,
    ):
        self.cursor.execute(
            """
        INSERT INTO statistics (chat_id, total_messages, deleted_messages, 
                              total_users, banned_users, last_updated)
        VALUES (?, 0, 0, 0, 0, CURRENT_TIMESTAMP)
        ON CONFLICT(chat_id) DO UPDATE SET
            total_messages = total_messages + ?,
            deleted_messages = deleted_messages + ?,
            total_users = total_users + ?,
            banned_users = banned_users + ?,
            last_updated = CURRENT_TIMESTAMP
        """,
            (
                chat_id,
                1 if messages else 0,
                1 if deleted else 0,
                1 if users else 0,
                1 if banned else 0,
            ),
        )
        self.connection.commit()

    def get_stats(self, chat_id: int):
        self.cursor.execute(
            """
        SELECT total_messages, deleted_messages, 
               total_users, banned_users 
        FROM statistics 
        WHERE chat_id = ?
        """,
            (chat_id,),
        )
        return self.cursor.fetchone() or (0, 0, 0, 0)

    def add_channel(self, chat_id: int, title: str):
        self.cursor.execute(
            "INSERT OR IGNORE INTO channels (chat_id, title, join_date) VALUES (?, ?, ?)",
            (chat_id, title, datetime.now()),
        )
        self.connection.commit()

    def remove_channel(self, chat_id: int):
        self.cursor.execute(
            "UPDATE channels SET is_active = 0 WHERE chat_id = ?", (chat_id,)
        )
        self.connection.commit()

    def get_all_channels(self):
        self.cursor.execute("SELECT chat_id, title FROM channels WHERE is_active = 1")
        return self.cursor.fetchall()

    def add_message(self, chat_id: int, user_id: int, message_text: str, is_spam: bool):
        self.cursor.execute(
            """
        INSERT INTO messages (chat_id, user_id, message_text, timestamp, is_spam)
        VALUES (?, ?, ?, ?, ?)
        """,
            (chat_id, user_id, message_text, datetime.now(), is_spam),
        )
        self.connection.commit()

    def add_chat_badword(self, chat_id: int, word: str, added_by: int) -> bool:
        """Добавляет запрещенное слово для конкретного чата"""
        word = re.compile(unidecode.unidecode(word.lower()), re.IGNORECASE)
        try:
            
            self.cursor.execute(
                """
                INSERT OR IGNORE INTO chat_badwords (chat_id, word, added_by, added_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, word, added_by, datetime.now())
            )
            self.connection.commit()
            return True
        except sqlite3.Error:
            return False

    def get_chat_badwords(self, chat_id: int) -> list[str]:
        """Получает список запрещенных слов для конкретного чата"""
        self.cursor.execute(
            "SELECT word FROM chat_badwords WHERE chat_id = ?",
            (chat_id,)
        )
        return [row[0] for row in self.cursor.fetchall()]
