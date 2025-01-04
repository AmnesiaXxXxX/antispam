import asyncio
import datetime
import sqlite3 as sql
from typing import Optional
import aiohttp
import os
from dotenv import load_dotenv

load_dotenv()

token = os.getenv("TOKEN") or exit("TOKEN is not set")


class User:
    def __init__(
        self,
        id: int,
        username: Optional[str] = None,
        reg_date: Optional[datetime.datetime] = None,
        ban: bool = False,
        ignore: bool = False
    ) -> None:
        if not id:
            raise ValueError("ID is not set")
        self.id = id
        self.username = username
        self.ban = ban
        self.ignore = ignore
        self.reg_date = reg_date or datetime.datetime.now()

    def __str__(self) -> str:
        return f"User(id={self.id}, username={self.username}, ban={self.ban}, ignore={self.ignore}, reg_date={self.reg_date})"


class Users:
    def __init__(self, db_name: str = "users.db"):
        try:
            self.db = sql.connect(db_name)
            self.cursor = self.db.cursor()
            # Ensure table exists
            self.cursor.execute(
                """CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    username TEXT,
                    ignore BOOLEAN,
                    banned BOOLEAN,
                    reg_date TEXT
                )"""
            )
            self.db.commit()
        except sql.Error as e:
            raise Exception(f"Database error: {e}")

    def add(self, user: User) -> bool:
        try:
            self.cursor.execute(
                """INSERT OR REPLACE INTO users (id, username, ignore, banned, reg_date)
                   VALUES (?, ?, ?, ?, ?)""",
                (user.id, user.username, user.ignore, user.ban, user.reg_date),
            )
            self.db.commit()
            return True
        except sql.Error as e:
            print(f"Error adding user to database: {e}")
            return False

    async def check(self, user_id: int, token: str = token ) -> Optional[User]:
        try:
            self.cursor.execute("SELECT * FROM users WHERE id = ?", (user_id,))
            row = self.cursor.fetchone()  # Fetch a single row
            # Выполняем запрос к FunStat API для получения данных пользователя
            async with aiohttp.ClientSession() as session:
                async with session.get(
                    f"http://funstat.org/api/v1/users/{user_id}/stats_min",
                    headers={"accept": "application/json", "Authorization": f"Bearer {token}"},
                ) as response:
                    if response.status != 200:
                        print(f"Error fetching data: {response.status}")
                        return None

                    try:
                        result = await response.json()
                        print(result)
                        first_msg_date_str = result.get("first_msg_date")
                        if not first_msg_date_str:
                            return None

                        # Преобразуем дату первого сообщения в объект datetime
                        first_msg_date = datetime.datetime.strptime(first_msg_date_str, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
                        delta = datetime.datetime.now(datetime.timezone.utc) - first_msg_date
                        
                        # Если с первого сообщения прошло больше 60 дней, игнорируем пользователя
                        if delta >= datetime.timedelta(days=60):
                            ignore = True
                        else:
                            ignore = False

                    except Exception as e:
                        print(f"Error parsing response JSON: {e}")
                        return None

            # Получаем данные из базы данных


            if row:
                user = User(
                    id=row[0],
                    username=row[1],
                    reg_date=row[1] if row[1] != first_msg_date else first_msg_date,
                    ignore=ignore,
                    ban=row[3],
                )
                return user
            else:
                print(f"User with ID {user_id} not found.")
                return None  # User not found

        except Exception as e:
            print(f"Exception occurred: {e}")
            return None

    def ban(self, user_id: int, ban: bool = True) -> bool:
        try:
            user = User(id=user_id, ban=ban)
            self.add(user)
            return True
        except sql.Error as e:
            print(f"Error banning user: {e}")
            return False


if __name__ == "__main__":
    try:
        users = Users()
        user = User(id=5957115070, reg_date=datetime.datetime.now())
        users.add(user)  # Здесь добавляем пользователя, а не баним
        users.ban(5957115070)  # Пример бана пользователя
        asyncio.run(users.check(5957115070))
    except Exception as e:
        print(f"An error occurred: {e}")
