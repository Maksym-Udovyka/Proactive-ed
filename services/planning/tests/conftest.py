import time
import uuid

import asyncpg
import jwt
import pytest

from app.core.config import get_settings
from app.main import create_app

API = "/api/planning/v1"


def make_token(user_id: int, expires_in: int = 3600) -> str:
    settings = get_settings()
    payload = {"sub": str(user_id), "exp": int(time.time()) + expires_in}
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


async def _create_user(conn: asyncpg.Connection) -> int:
    # отрицательные telegram_id не пересекаются с id реальных пользователей
    telegram_id = -(1 + uuid.uuid4().int % 10**12)
    return await conn.fetchval(
        """
        INSERT INTO auth.users (telegram_id, first_name)
        VALUES ($1, 'Test') RETURNING user_id
        """,
        telegram_id,
    )


@pytest.fixture
async def db():
    conn = await asyncpg.connect(get_settings().database_url)
    yield conn
    await conn.close()


@pytest.fixture
async def user(db):
    """Тестовый пользователь. После теста удаляется вместе со всеми его данными."""
    user_id = await _create_user(db)
    yield user_id
    await db.execute("DELETE FROM auth.users WHERE user_id = $1", user_id)


@pytest.fixture
async def other_user(db):
    user_id = await _create_user(db)
    yield user_id
    await db.execute("DELETE FROM auth.users WHERE user_id = $1", user_id)


@pytest.fixture
def auth_headers(user):
    return {"Authorization": f"Bearer {make_token(user)}"}


@pytest.fixture
def other_headers(other_user):
    return {"Authorization": f"Bearer {make_token(other_user)}"}


@pytest.fixture
async def client(aiohttp_client):
    return await aiohttp_client(create_app())


@pytest.fixture
async def plan(client, auth_headers):
    """План, созданный тестовым пользователем."""
    response = await client.post(
        f"{API}/plans", json={"title": "Test plan"}, headers=auth_headers
    )
    assert response.status == 201
    return await response.json()