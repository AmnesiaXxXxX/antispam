import sqlite3
from datetime import datetime
from src.utils.logger_config import logger
import unidecode
import re


class Database:
    def __init__(self, db_file):
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self.create_tables()

    def create_tables(self):
        # Таблица для всех пользователей
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            join_date TIMESTAMP,
            spam_count INTEGER DEFAULT 0,
            is_banned BOOLEAN DEFAULT 0,
            ban_pending BOOLEAN DEFAULT 0
        )""")

        # Обновленная таблица verified_users с новыми полями
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS verified_users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            verified_at TIMESTAMP,
            first_message_date TEXT,
            messages_count INTEGER,
            chats_count INTEGER
        )""")

        # Таблица для каналов
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS chats (
            chat_id INTEGER PRIMARY KEY,
            title TEXT,
            join_date TIMESTAMP,
            settings TEXT,
            is_active BOOLEAN DEFAULT 1
        )""")

        # Таблица для сообщений с внешним ключом на verified_users
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            user_id INTEGER,
            message_text TEXT,
            timestamp TIMESTAMP,
            is_spam BOOLEAN,
            FOREIGN KEY (chat_id) REFERENCES chats (chat_id),
            FOREIGN KEY (user_id) REFERENCES verified_users (user_id)
        )""")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS statistics (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER UNIQUE,
            total_messages INTEGER DEFAULT 0,
            deleted_messages INTEGER DEFAULT 0,
            total_users INTEGER DEFAULT 0,
            banned_users INTEGER DEFAULT 0,
            last_updated TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (chat_id)
        )""")

        # Обновляем таблицу chat_badwords с внешним ключом
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS chat_badwords (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            word TEXT,
            added_by INTEGER,
            added_at TIMESTAMP,
            FOREIGN KEY (chat_id) REFERENCES chats (chat_id),
            FOREIGN KEY (added_by) REFERENCES verified_users (user_id),
            UNIQUE(chat_id, word)
        )""")

        # Таблица для спам-предупреждений
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS spam_warnings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            chat_id INTEGER,
            message_text TEXT,
            warning_date TIMESTAMP,
            is_confirmed BOOLEAN DEFAULT 0,
            FOREIGN KEY (user_id) REFERENCES users (user_id),
            FOREIGN KEY (chat_id) REFERENCES chats (chat_id)
        )""")
        self.cursor.execute("""
        CREATE TABLE IF NOT EXISTS banwords_preset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            words TEXT,
            name TEXT
        )""")

        # Добавляем индексы для оптимизации
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_badwords_added_by ON chat_badwords(added_by)"
        )

        self.connection.commit()

    def get_admins(self):
        self.cursor.execute("SELECT user_id FROM users WHERE admin = 1")
        return [row[0] for row in self.cursor.fetchall()]
    
    def update_stats(
        self,
        chat_id: int,
        messages: bool = False,
        deleted: bool = False,
        users: bool = False,
        banned: bool = False,
    ):
        # Выполняем вставку или обновление значений
        self.cursor.execute(
            """
            INSERT INTO statistics (chat_id, total_messages, deleted_messages, 
                                    total_users, banned_users, last_updated)
            VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(chat_id) DO UPDATE SET
                total_messages = total_messages + EXCLUDED.total_messages,
                deleted_messages = deleted_messages + EXCLUDED.deleted_messages,
                total_users = total_users + EXCLUDED.total_users,
                banned_users = banned_users + EXCLUDED.banned_users,
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

    def get_stats(self, chat_id):
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

    def add_chat(self, chat_id: int, title):
        self.cursor.execute(
            "INSERT OR IGNORE INTO chats (chat_id, title, join_date) VALUES (?, ?, ?)",
            (chat_id, title, datetime.now()),
        )
        self.connection.commit()

    def remove_chat(self, chat_id):
        self.cursor.execute(
            "UPDATE chats SET is_active = 0 WHERE chat_id = ?", (chat_id,)
        )
        self.connection.commit()

    def get_all_chats(self):
        self.cursor.execute("SELECT chat_id, title FROM chats WHERE is_active = 1")
        return self.cursor.fetchall()

    def add_message(self, chat_id: int, user_id: int, message_text: str, is_spam):
        self.cursor.execute(
            """
        INSERT INTO messages (chat_id, user_id, message_text, timestamp, is_spam)
        VALUES (?, ?, ?, ?, ?)
        """,
            (chat_id, user_id, message_text, datetime.now(), is_spam),
        )
        self.connection.commit()

    def add_chat_badword(self, chat_id: int, word: str, added_by) -> bool:
        """Добавляет запрещенное слово для конкретного чата"""

        def is_regex_pattern(s):
            try:
                re.compile(s)
                return True
            except re.error:
                return False

        # Заменить строку:
        word = unidecode.unidecode(word.lower())
        if not is_regex_pattern(word):
            word = re.escape(word)
        try:
            self.cursor.execute(
                """
                INSERT OR IGNORE INTO chat_badwords (chat_id, word, added_by, added_at)
                VALUES (?, ?, ?, ?)
                """,
                (chat_id, word, added_by, datetime.now()),
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding bad word: {e}")
            return False

    def get_chat_badwords(self, chat_id) -> list[str]:
        """Получает список запрещенных слов для конкретного чата"""
        self.cursor.execute(
            "SELECT word FROM chat_badwords WHERE chat_id = ?", (chat_id,)
        )
        return [row[0] for row in self.cursor.fetchall()]

    def add_verified_user(self, user_id: int, user_data) -> bool:
        """Добавляет проверенного пользователя в базу данных"""
        try:
            self.cursor.execute(
                """
            INSERT OR REPLACE INTO verified_users 
            (user_id, first_name, username, verified_at, first_message_date, 
             messages_count, chats_count)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
            """,
                (
                    user_id,
                    user_data.get("first_name", ""),
                    user_data.get("username", ""),
                    user_data.get("first_msg_date"),
                    user_data.get("messages_count", 0),
                    user_data.get("chats_count", 0),
                ),
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding verified user: {e}")
            return False

    def is_user_verified(self, user_id) -> bool:
        """
        Проверяет, является ли пользователь проверенным
        """
        self.cursor.execute(
            "SELECT user_id FROM verified_users WHERE user_id = ?", (user_id,)
        )
        return bool(self.cursor.fetchone())

    def add_user(
        self, user_id: int, first_name: str | None = None, username: str | None = None
    ) -> bool:
        """Добавляет нового пользователя или обновляет существующего"""
        try:
            self.cursor.execute(
                """
            INSERT INTO users (user_id, first_name, username, join_date)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(user_id) DO UPDATE SET
                first_name = ?,
                username = ?
            """,
                (user_id, first_name, username, first_name, username),
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding user: {e}")
            return False

    def add_spam_warning(self, user_id: int, chat_id: int, message_text) -> bool:
        """Добавляет предупреждение о спаме и проверяет количество нарушений"""
        try:
            self.cursor.execute(
                """
            INSERT INTO spam_warnings (user_id, chat_id, message_text, warning_date)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            """,
                (user_id, chat_id, message_text),
            )

            # Увеличиваем счетчик спама
            self.cursor.execute(
                """
            UPDATE users 
            SET spam_count = spam_count + 1,
                ban_pending = CASE WHEN spam_count + 1 >= 3 THEN 1 ELSE 0 END
            WHERE user_id = ?
            """,
                (user_id,),
            )

            self.connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding spam warning: {e}")
            return False

    def get_pending_bans(self) -> list:
        """Получает список пользователей, ожидающих бана"""
        self.cursor.execute("""
        SELECT user_id, first_name, username, spam_count 
        FROM users 
        WHERE ban_pending = 1 AND is_banned = 0
        """)
        return self.cursor.fetchall()

    def confirm_ban(self, user_id) -> bool:
        """Подтверждает бан пользователя администратором"""
        try:
            self.cursor.execute(
                """
            UPDATE users 
            SET is_banned = 1, ban_pending = 0
            WHERE user_id = ?
            """,
                (user_id,),
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error confirming ban: {e}")
            return False

    def reject_ban(self, user_id) -> bool:
        """Отклоняет бан пользователя"""
        try:
            self.cursor.execute(
                """
            UPDATE users 
            SET spam_count = 0, ban_pending = 0
            WHERE user_id = ?
            """,
                (user_id,),
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error rejecting ban: {e}")
            return False

    def is_user_banned(self, user_id) -> bool:
        """Проверяет, забанен ли пользователь"""
        self.cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return bool(result and result[0])


db = Database("antispam.db")


