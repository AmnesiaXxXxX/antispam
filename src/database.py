import os
import re
import sqlite3
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, date
from typing import List, Optional, Union, Tuple

import matplotlib.pyplot as plt
import numpy as np
import unidecode
from matplotlib.dates import DateFormatter, date2num
from matplotlib.ticker import MaxNLocator
from scipy.interpolate import make_interp_spline

from src.utils.logger_config import logger


def smooth_line(
    x: Union[np.ndarray, list], y: Union[np.ndarray, list], num_points: int = 300
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Функция выполняет кубическую интерполяцию (сплайн) для сглаживания линий.

    :param x: Набор исходных значений по оси X (список или массив NumPy).
    :param y: Набор исходных значений по оси Y (список или массив NumPy).
    :param num_points: Количество точек, до которого нужно расширить/интерполировать данные.
    :return: Кортеж из двух массивов NumPy (x_new, y_smooth), где:
             - x_new: Новый набор точек по оси X,
             - y_smooth: Интерполированные (сглаженные) значения по оси Y.
    """
    x_array = np.array(x, dtype=float)
    y_array = np.array(y, dtype=float)

    x_new = np.linspace(x_array.min(), x_array.max(), num_points)
    spl = make_interp_spline(x_array, y_array, k=3)  # Кубический сплайн
    y_smooth = spl(x_new)
    return x_new, y_smooth


def generate_plot(data: Tuple[int, List[Tuple[str]], List[Tuple[str]], str]) -> str:
    """
    Генерирует и сохраняет график, показывающий динамику сообщений по датам и удалённых (спам) сообщений.

    :param data: Кортеж вида (chat_id, raw_dates, raw_deleted_dates, output_dir), где:
                 - chat_id: Идентификатор чата (целое число),
                 - raw_dates: Список кортежей с датами (строки), когда были написаны сообщения,
                 - raw_deleted_dates: Список кортежей с датами (строки), когда сообщения были помечены как спам,
                 - output_dir: Путь к директории, в которую следует сохранить итоговый график.
    :return: Путь к сохранённому графику (строка).
    """
    chat_id, raw_dates, raw_deleted_dates, output_dir = data

    # Преобразуем даты в объекты datetime.date
    dates: List[date] = [
        datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").date() for row in raw_dates
    ]

    # Подсчёт количества сообщений по дням
    daily_messages: defaultdict[date, int] = defaultdict(int)
    for d in dates:
        daily_messages[d] += 1

    # Подсчёт удалённых (спам) сообщений по дням
    daily_deleted_messages: defaultdict[date, int] = defaultdict(int)
    for row in raw_deleted_dates:
        d = datetime.strptime(row[0], "%Y-%m-%d %H:%M:%S").date()
        daily_deleted_messages[d] += 1

    # Преобразуем даты в числовой формат для графика
    dates_numeric = date2num(list(daily_messages.keys()))
    deleted_dates_numeric = date2num(list(daily_deleted_messages.keys()))

    # Построение графика
    with plt.style.context("dark_background"):
        fig, ax = plt.subplots(figsize=(20, 10))

        ax.plot(
            dates_numeric,
            list(daily_messages.values()),
            label="Всего сообщений",
        )
        ax.plot(
            deleted_dates_numeric,
            list(daily_deleted_messages.values()),
            label="Удалено сообщений",
        )

        # Настройки графика
        ax.set_title(f"Статистика для чата {chat_id} за всё время", fontsize=20)
        ax.set_xlabel("Дата", fontsize=16)
        ax.set_ylabel("Количество", fontsize=16)
        ax.legend(fontsize=12)
        ax.grid(axis="y", linestyle="--", alpha=0.85)
        ax.xaxis.set_major_locator(MaxNLocator(10))

        # Форматирование оси X
        date_formatter = DateFormatter("%Y-%m-%d")
        ax.xaxis.set_major_formatter(date_formatter)
        plt.xticks(rotation=45)

        # Сохранение графика
        os.makedirs(output_dir, exist_ok=True)
        file_path = os.path.join(output_dir, f"chat_{chat_id}_stats_over_time.png")
        plt.savefig(file_path, dpi=300)
        plt.close(fig)

    return file_path


class Database:
    """
    Класс для работы с базой данных SQLite, обеспечивающий хранение и управление
    информацией о чатах, пользователях, сообщениях и статистике.
    """

    def __init__(self, db_file: str) -> None:
        """
        Конструктор. Устанавливает соединение с файлом базы данных и создаёт таблицы (если их нет).

        :param db_file: Путь к файлу базы данных (строка).
        """
        self.connection = sqlite3.connect(db_file)
        self.cursor = self.connection.cursor()
        self.create_tables()

    def create_tables(self) -> None:
        """
        Создаёт основные таблицы в базе данных, если они ещё не созданы.
        Включает в себя таблицы: users, verified_users, chats, messages, statistics,
        chat_badwords, spam_warnings, banwords_preset.

        :return: None
        """
        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                hashed_user_id TEXT,
                first_name TEXT,
                username TEXT,
                join_date TIMESTAMP,
                spam_count INTEGER DEFAULT 0,
                is_banned BOOLEAN DEFAULT 0,
                ban_pending BOOLEAN DEFAULT 0,
                admin BOOLEAN DEFAULT 0
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS verified_users (
                user_id INTEGER PRIMARY KEY,
                hashed_user_id TEXT,
                first_name TEXT,
                username TEXT,
                verified_at TIMESTAMP,
                first_message_date TEXT,
                messages_count INTEGER,
                chats_count INTEGER
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                chat_id INTEGER PRIMARY KEY,
                hashed_chat_id TEXT,
                title TEXT,
                join_date TIMESTAMP,
                settings TEXT,
                is_active BOOLEAN DEFAULT 1
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                user_id INTEGER,
                message_text TEXT,
                timestamp TIMESTAMP,
                is_spam BOOLEAN,
                link TEXT,
                FOREIGN KEY (chat_id) REFERENCES chats (chat_id),
                FOREIGN KEY (user_id) REFERENCES verified_users (user_id)
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS statistics (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER UNIQUE,
                total_messages INTEGER DEFAULT 0,
                deleted_messages INTEGER DEFAULT 0,
                total_users INTEGER DEFAULT 0,
                banned_users INTEGER DEFAULT 0,
                last_updated TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (chat_id)
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS chat_badwords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER,
                word TEXT,
                added_by INTEGER,
                added_at TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES chats (chat_id),
                FOREIGN KEY (added_by) REFERENCES verified_users (user_id),
                UNIQUE(chat_id, word)
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS spam_warnings (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER,
                chat_id INTEGER,
                message_text TEXT,
                warning_date TIMESTAMP,
                is_confirmed BOOLEAN DEFAULT 0,
                FOREIGN KEY (user_id) REFERENCES users (user_id),
                FOREIGN KEY (chat_id) REFERENCES chats (chat_id)
            )
            """
        )

        self.cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS banwords_preset (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                words TEXT,
                name TEXT
            )
            """
        )

        # Создание индексов для повышения производительности некоторых запросов
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_messages_user_id ON messages(user_id)"
        )
        self.cursor.execute(
            "CREATE INDEX IF NOT EXISTS idx_chat_badwords_added_by ON chat_badwords(added_by)"
        )

        self.connection.commit()

    def update_stats(
        self,
        chat_id: int,
        messages: bool = False,
        deleted: bool = False,
        users: bool = False,
        banned: bool = False,
    ) -> None:
        """
        Обновляет статистику чата (statistics) в соответствии с переданными флагами.
        Каждому флагу соответствует инкремент определённого поля:
          - messages -> total_messages
          - deleted -> deleted_messages
          - users -> total_users
          - banned -> banned_users

        :param chat_id: Идентификатор чата, для которого обновляется статистика.
        :param messages: Увеличить счётчик total_messages на 1 (по умолчанию False).
        :param deleted: Увеличить счётчик deleted_messages на 1 (по умолчанию False).
        :param users: Увеличить счётчик total_users на 1 (по умолчанию False).
        :param banned: Увеличить счётчик banned_users на 1 (по умолчанию False).
        :return: None
        """
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

    def get_most_common_word(
        self,
        min_len: Optional[int] = 3,
        max_len: Optional[int] = 10,
        limit: Optional[int] = None,
        reverse: bool = False,
    ) -> str:
        """
        Возвращает список самых (или наименее) часто встречающихся слов в базе (таблица messages),
        удовлетворя критериям длины.

        :param min_len: Минимальная длина слова (по умолчанию 3).
        :param max_len: Максимальная длина слова (по умолчанию 10).
        :param limit: Количество результирующих слов (None, если ограничения нет).
        :param reverse: Порядок сортировки. Если True, то сортируем по возрастанию частоты.
                        Если False, то по убыванию (наиболее частые).
        :return: Строка, где каждая строка содержит слово и его счётчик, разделённые двоеточием.
        """
        try:
            self.cursor.execute("SELECT message_text FROM messages")
            rows = self.cursor.fetchall()

            # Объединяем весь текст
            all_text = " ".join(row[0] for row in rows if row[0])
            words = re.findall(r"\w+", all_text.lower())

            # Фильтрация слов по длине
            filtered_words = [word for word in words if min_len <= len(word) <= max_len]

            # Подсчёт частот
            word_counts: Counter[str] = Counter(filtered_words)

            # Сортировка по частоте (если reverse=True, то сортируем по возрастанию)
            sorted_words = sorted(
                word_counts.items(), key=lambda x: x[1], reverse=not reverse
            )

            # Ограничение количества
            if limit:
                sorted_words = sorted_words[:limit]

            # Формирование строки результата
            result = "\n".join([f"{word}: {count}" for word, count in sorted_words])
            return result

        except Exception as e:
            return str(e)

    def get_admins(self) -> List[int]:
        """
        Получает список идентификаторов пользователей, у которых в таблице users admin = 1.

        :return: Список идентификаторов (user_id) администраторов (List[int]).
        """
        self.cursor.execute("SELECT user_id FROM users WHERE admin = 1")
        return [row[0] for row in self.cursor.fetchall()]

    def get_stats(self, chat_id: int) -> Tuple[int, int]:
        """
        Получает статистику по конкретному чату: total_messages и deleted_messages.

        :param chat_id: Идентификатор чата (int).
        :return: Кортеж (total_messages, deleted_messages). Если нет записей, возвращается (0, 0).
        """
        self.cursor.execute(
            """
            SELECT total_messages, deleted_messages
            FROM statistics
            WHERE chat_id = ?
            """,
            (chat_id,),
        )
        return self.cursor.fetchone() or (0, 0)

    # ===========================
    # Работа с чатом
    # ===========================
    def add_chat(self, chat_id: int, title: str) -> None:
        """
        Добавляет новый чат в таблицу chats, если его нет.
        При этом сохраняется захешированный chat_id в hashed_chat_id.

        :param chat_id: Идентификатор чата (int).
        :param title: Название чата (str).
        :return: None
        """
        self.cursor.execute(
            """
            INSERT OR IGNORE INTO chats (chat_id, title, join_date)
            VALUES (?, ?, ?, ?)
            """,
            (chat_id, title, datetime.now()),
        )
        self.connection.commit()

    def remove_chat(self, chat_id: int) -> None:
        """
        Помечает чат как неактивный (is_active = 0).

        :param chat_id: Идентификатор чата (int).
        :return: None
        """
        self.cursor.execute(
            "UPDATE chats SET is_active = 0 WHERE chat_id = ?", (chat_id,)
        )
        self.connection.commit()

    def get_all_chats(self) -> List[Tuple[int, str]]:
        """
        Получает список всех активных чатов (is_active = 1).

        :return: Список кортежей (chat_id, title).
        """
        self.cursor.execute("SELECT chat_id, title FROM chats WHERE is_active = 1")
        return self.cursor.fetchall()

    # ===========================
    # Работа с сообщениями
    # ===========================
    def add_message(
        self,
        chat_id: int,
        user_id: int,
        message_text: str,
        is_spam: bool,
        link: Optional[str] = None,
    ) -> None:
        """
        Добавляет новое сообщение в таблицу messages.

        :param chat_id: Идентификатор чата (int).
        :param user_id: Идентификатор пользователя (int).
        :param message_text: Текст сообщения (str).
        :param is_spam: Флаг, указывающий, является ли сообщение спамом (bool).
        :param link: Ссылка (URL) при необходимости (например, если в сообщении обнаружена ссылка).
        :return: None
        """
        self.cursor.execute(
            """
            INSERT INTO messages (chat_id, user_id, message_text, timestamp, is_spam, link)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (chat_id, user_id, message_text, datetime.now(), is_spam, link),
        )
        self.connection.commit()

    # ===========================
    # Работа с плохими словами
    # ===========================
    def add_chat_badword(self, chat_id: int, word: str, added_by: int) -> bool:
        """
        Добавляет "плохое слово" (запрещённое) в таблицу chat_badwords.
        При необходимости экранирует строку регулярного выражения, если оно невалидно.

        :param chat_id: Идентификатор чата (int).
        :param word: Слово или паттерн, который нужно запретить (str).
        :param added_by: Идентификатор пользователя, добавившего слово (int).
        :return: True, если вставка прошла успешно, иначе False.
        """

        def is_regex_pattern(s: str) -> bool:
            try:
                re.compile(s)
                return True
            except re.error:
                return False

        # Приводим слово к нижнему регистру и убираем акценты (unidecode)
        word = unidecode.unidecode(word.lower())
        # Если это невалидный паттерн, экранируем
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

    def get_chat_badwords(self, chat_id: int) -> List[str]:
        """
        Возвращает список всех запрещённых слов (паттернов) для указанного чата.

        :param chat_id: Идентификатор чата (int).
        :return: Список строк (List[str]) — слова/паттерны в нижнем регистре.
        """
        self.cursor.execute(
            "SELECT word FROM chat_badwords WHERE chat_id = ?", (chat_id,)
        )
        return [row[0].lower().replace(" ", "") for row in self.cursor.fetchall()]

    # ===========================
    # Работа с пользователями
    # ===========================
    def get_user(self, user_id: int) -> Optional[Tuple]:
        """
        Получает запись пользователя из таблицы users по его user_id.

        :param user_id: Идентификатор пользователя (int).
        :return: Кортеж с данными пользователя или None, если пользователь не найден.
        """
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()

    def get_user_messages_count(self, user_id: int) -> int:
        """
        Подсчитывает количество сообщений, отправленных пользователем.

        :param user_id: Идентификатор пользователя (int).
        :return: Количество сообщений (int).
        """
        self.cursor.execute(
            "SELECT COUNT(*) FROM messages WHERE user_id = ?", (user_id,)
        )
        return self.cursor.fetchone()[0]

    def add_verified_user(self, user_id: int, user_data: dict) -> bool:
        """
        Добавляет (или обновляет) запись о пользователе в таблице verified_users.
        Используется для отметки "проверенного" пользователя.

        :param user_id: Идентификатор пользователя (int).
        :param user_data: Словарь с дополнительными данными, такими как:
                          {
                              "first_name": <str>,
                              "username": <str>,
                              "first_msg_date": <str>,
                              "messages_count": <int>,
                              "chats_count": <int>
                          }
        :return: True при успешном добавлении/обновлении, False при ошибке.
        """
        try:
            self.cursor.execute(
                """
                INSERT OR REPLACE INTO verified_users
                (user_id, first_name, username, verified_at,
                 first_message_date, messages_count, chats_count)
                VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP, ?, ?, ?)
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

    def is_user_verified(self, user_id: int) -> bool:
        """
        Проверяет, присутствует ли пользователь в таблице verified_users.

        :param user_id: Идентификатор пользователя (int).
        :return: True, если пользователь найден, иначе False.
        """
        self.cursor.execute(
            "SELECT user_id FROM verified_users WHERE user_id = ?", (user_id,)
        )
        return bool(self.cursor.fetchone())

    def add_user(
        self,
        user_id: int,
        first_name: Optional[str] = None,
        username: Optional[str] = None,
    ) -> bool:
        """
        Добавляет или обновляет запись пользователя в таблице users.

        :param user_id: Идентификатор пользователя (int).
        :param first_name: Имя пользователя (str) или None.
        :param username: Username пользователя (str) или None.
        :return: True, если операция прошла успешно, иначе False.
        """
        try:
            self.cursor.execute(
                """
                INSERT INTO users (user_id, first_name, username, join_date)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                ON CONFLICT(user_id) DO UPDATE SET
                    first_name = excluded.first_name,
                    username = excluded.username
                """,
                (user_id, first_name, username),
            )
            self.connection.commit()
            return True
        except sqlite3.Error as e:
            logger.error(f"Error adding user: {e}")
            return False

    # ===========================
    # Предупреждения о спаме и баны
    # ===========================
    def add_spam_warning(self, user_id: int, chat_id: int, message_text: str) -> bool:
        """
        Добавляет запись о предупреждении спама (spam_warnings) и инкрементирует счётчик
        spam_count в таблице users. Если счётчик достигает 3, устанавливается ban_pending = 1.

        :param user_id: Идентификатор пользователя (int).
        :param chat_id: Идентификатор чата (int).
        :param message_text: Текст сообщения, вызвавшего предупреждение (str).
        :return: True, если успешно добавлено предупреждение, False при ошибке.
        """
        try:
            self.cursor.execute(
                """
                INSERT INTO spam_warnings (user_id, chat_id, message_text, warning_date)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (user_id, chat_id, message_text),
            )
            # Увеличиваем spam_count
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

    def get_pending_bans(self) -> List[int]:
        """
        Получает список user_id пользователей, у которых spam_count >= 3 и они не являются администраторами.

        :return: Список идентификаторов пользователей (List[int]).
        """
        self.cursor.execute(
            """
            SELECT user_id
            FROM users
            WHERE spam_count >= 3 AND admin = 0
            """
        )
        result = [user[0] for user in self.cursor.fetchall()]
        return result

    def confirm_ban(self, user_id: int) -> bool:
        """
        Подтверждает бан пользователя (is_banned = 1, ban_pending = 0).

        :param user_id: Идентификатор пользователя (int).
        :return: True, если обновление прошло успешно, иначе False.
        """
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

    def reject_ban(self, user_id: int) -> bool:
        """
        Сбрасывает счётчик спама и убирает ожидание бана (ban_pending) у пользователя.

        :param user_id: Идентификатор пользователя (int).
        :return: True, если обновление прошло успешно, иначе False.
        """
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

    def search(self, text: str | Optional[List[str]]) -> str:

        if isinstance(text, list):
            text = " ".join(text)
        self.cursor.execute(
            """SELECT user_id, message_text
                FROM messages
                WHERE lower(message_text)
                LIKE '% ' || lower(?) || ' %'
                LIMIT 10;""",
            (text,),
        )
        return "\n".join(map(str, self.cursor.fetchall()))

    def is_user_banned(self, user_id: int) -> bool:
        """
        Проверяет, забанен ли пользователь в системе (is_banned = 1).

        :param user_id: Идентификатор пользователя (int).
        :return: True, если пользователь забанен, иначе False.
        """
        self.cursor.execute("SELECT is_banned FROM users WHERE user_id = ?", (user_id,))
        result = self.cursor.fetchone()
        return bool(result and result[0])

    def find_users_who_wrote_words(
        self, words: Union[str, List[str]]
    ) -> List[Tuple[int, str, Optional[str], str]]:
        """
        Ищет пользователей, которые в своих сообщениях (таблица messages) употребляли
        указанные слово или слова. Возвращает список кортежей, где каждый кортеж содержит:
        (user_id, first_name, username, текст сообщения).

        :param words: Слово (str) или список слов (List[str]) для поиска.
        :return: Список кортежей (user_id, first_name, username, message_text).
        """
        if isinstance(words, str):
            words_list = [words]
        else:
            words_list = words

        # Формируем условия вида "m.message_text LIKE ?" для каждого слова
        conditions = []
        placeholders = []
        for w in words_list:
            conditions.append("m.message_text LIKE ?")
            placeholders.append(f"%{w}%")

        # Объединяем условия через OR
        where_clause = " OR ".join(conditions)

        query = f"""
            SELECT u.user_id, u.first_name, u.username, m.message_text
            FROM messages m
            JOIN users u ON m.user_id = u.user_id
            WHERE {where_clause}
        """

        try:
            self.cursor.execute(query, placeholders)
            return self.cursor.fetchall()
        except sqlite3.Error as e:
            logger.error(f"Ошибка при поиске пользователей по словам: {e}")
            return []

    # ===========================
    # Генерация графиков
    # ===========================
    def get_stats_graph(
        self,
        chat_id: Union[int, List[int]],
        output_dir: str = "src/stats/",
    ) -> Union[str, List[str], bool]:
        """
        Создаёт графики для одного или нескольких чатов и сохраняет их в директории output_dir.
        Использует многопоточность для одновременной генерации нескольких графиков.

        :param chat_id: Целое число (один чат) или список идентификаторов чатов.
        :param output_dir: Путь к директории, куда сохраняются графики (str).
        :return: Строка с путём к графику (если чатов один), список строк (если чатов несколько),
                 или False, если данные отсутствуют.
        """
        tasks = []
        if isinstance(chat_id, int):
            chat_ids = [chat_id]
        else:
            chat_ids = chat_id  # type: ignore

        # Формируем задачи для каждого чата
        for c_id in chat_ids:
            # Получение всех сообщений для чата
            self.cursor.execute(
                "SELECT datetime(timestamp, 'localtime') FROM messages WHERE chat_id = ? ORDER BY timestamp",
                (c_id,),
            )
            raw_dates = self.cursor.fetchall()

            # Получение всех удалённых (спам) сообщений для чата
            self.cursor.execute(
                """
                SELECT datetime(timestamp, 'localtime')
                FROM messages
                WHERE chat_id = ? AND is_spam = 1
                ORDER BY timestamp
                """,
                (c_id,),
            )
            raw_deleted_dates = self.cursor.fetchall()

            if raw_dates:
                tasks.append((c_id, raw_dates, raw_deleted_dates, output_dir))
            else:
                logger.info(f"No data found for chat_id {c_id}.")

        results = []
        with ThreadPoolExecutor(max_workers=32) as executor:
            futures = [executor.submit(generate_plot, task) for task in tasks]
            for future in as_completed(futures):
                try:
                    results.append(future.result())
                except Exception as e:
                    logger.info(f"Error during graph generation: {e}")

        if not results:
            return False
        return results[0] if len(results) == 1 else results


# Инициализация базы
db = Database("antispam.db")
