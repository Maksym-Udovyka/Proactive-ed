import asyncpg

_COLUMNS = "user_id, telegram_id, first_name, username, language_code, timezone"


class UserRepository:
    def __init__(self, pool: asyncpg.Pool):
        self.pool = pool

    async def upsert_telegram_user(self, telegram_id: int, first_name: str,
                                   username: str | None, language_code: str) -> dict:
        """Атомарно створює користувача або оновлює ім'я/username (без гонки SELECT→INSERT).
        Мову й часовий пояс, які користувач міг змінити в профілі, не перезаписує."""
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"""
                INSERT INTO auth.users (telegram_id, first_name, username, language_code)
                VALUES ($1, $2, $3, $4)
                ON CONFLICT (telegram_id) DO UPDATE
                    SET first_name = EXCLUDED.first_name,
                        username   = EXCLUDED.username
                RETURNING {_COLUMNS};
                """,
                telegram_id, first_name, username, language_code,
            )
            return dict(row)

    async def get_user_by_id(self, user_id: int) -> dict | None:
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(f"SELECT {_COLUMNS} FROM auth.users WHERE user_id = $1;", user_id)
            return dict(row) if row else None

    async def update_profile(self, user_id: int, fields: dict) -> dict | None:
        """Оновлює дозволені поля профілю. Імена колонок беруться лише з білого списку."""
        allowed = ("first_name", "language_code", "timezone")
        items = [(k, v) for k, v in fields.items() if k in allowed]
        if not items:
            return await self.get_user_by_id(user_id)
        assignments = ", ".join(f"{k} = ${i}" for i, (k, _) in enumerate(items, start=2))
        async with self.pool.acquire() as conn:
            row = await conn.fetchrow(
                f"UPDATE auth.users SET {assignments} WHERE user_id = $1 RETURNING {_COLUMNS};",
                user_id, *[v for _, v in items],
            )
            return dict(row) if row else None
