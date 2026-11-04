import asyncpg

_COLUMNS = "user_id, telegram_id, first_name, display_name, username, language_code, timezone"


def _to_user(row) -> dict:
    """Рядок БД -> словник. name = ім'я, яке бачать люди: display_name, інакше ім'я з Telegram."""
    user = dict(row)
    user["name"] = user.get("display_name") or user["first_name"]
    return user


class UserRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def upsert_telegram_user(self, telegram_id: int, first_name: str,
                                   username: str | None, language_code: str) -> dict:
        """Знаходить користувача або створює нового.

        Спочатку SELECT: INSERT ... ON CONFLICT бере значення з лічильника user_id ще до
        перевірки конфлікту, тому кожен повторний вхід "спалював" би один номер.
        Тепер INSERT виконується лише для справді нового користувача.
        first_name/username синхронізуються з Telegram, лише якщо змінились.
        display_name, мову й часовий пояс не чіпаємо: це вибір самого користувача.
        """
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"SELECT {_COLUMNS} FROM auth.users WHERE telegram_id = $1;", telegram_id)
            if row:
                if row["first_name"] != first_name or row["username"] != username:
                    row = await conn.fetchrow(
                        f"UPDATE auth.users SET first_name = $2, username = $3 "
                        f"WHERE telegram_id = $1 RETURNING {_COLUMNS};",
                        telegram_id, first_name, username)
                return _to_user(row)

            row = await conn.fetchrow(
                f"""
                INSERT INTO auth.users (telegram_id, first_name, username, language_code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (telegram_id) DO NOTHING
                RETURNING {_COLUMNS};
                """,
                telegram_id, first_name, username, language_code,
            )
            if row is None:  # рідкісна гонка: паралельний запит створив користувача першим
                row = await conn.fetchrow(
                    f"SELECT {_COLUMNS} FROM auth.users WHERE telegram_id = $1;", telegram_id)
            return _to_user(row)

    async def get_user_by_id(self, user_id: int) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {_COLUMNS} FROM auth.users WHERE user_id = $1;", user_id)
            return _to_user(row) if row else None

    async def update_profile(self, user_id: int, fields: dict) -> dict | None:
        """Оновлює дозволені поля профілю. Імена колонок беруться лише з білого списку.

        Значення None допустиме: для display_name воно скидає ім'я до Telegram-імені.
        """
        allowed = ("display_name", "language_code", "timezone")
        items = [(k, v) for k, v in fields.items() if k in allowed]
        if not items:
            return await self.get_user_by_id(user_id)
        assignments = ", ".join(f"{k} = ${i}" for i, (k, _) in enumerate(items, start=2))
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE auth.users SET {assignments} WHERE user_id = $1 RETURNING {_COLUMNS};",
                user_id, *[v for _, v in items],
            )
            return _to_user(row) if row else None

    async def get_public_profiles(self, user_ids: list[int]) -> list[dict]:
        """Публічні дані користувачів: тільки user_id та ім'я, яке бачать інші."""
        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                "SELECT user_id, display_name, first_name FROM auth.users "
                "WHERE user_id = ANY($1::bigint[]) ORDER BY user_id;",
                user_ids,
            )
        return [{"user_id": r["user_id"], "name": r["display_name"] or r["first_name"]}
                for r in rows]
