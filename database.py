import sqlite3
from datetime import datetime


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

        self.connection.commit()

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
