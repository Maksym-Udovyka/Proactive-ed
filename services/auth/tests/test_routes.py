import pytest

from app.core.config import Settings
from app.main import create_app
from tests.helpers import make_init_data

BOT = "123456:TEST-TOKEN"
USER = {"id": 42, "first_name": "Іван", "username": "ivan", "language_code": "uk"}


class FakeRepo:
    def __init__(self):
        self.users = {}

    async def upsert_telegram_user(self, telegram_id, first_name, username, language_code):
        u = self.users.setdefault(telegram_id, {"user_id": len(self.users) + 1, "telegram_id": telegram_id,
                                                "language_code": language_code, "timezone": "Europe/Kyiv"})
        u.update(first_name=first_name, username=username)
        return dict(u)

    async def get_user_by_id(self, user_id):
        return next((dict(u) for u in self.users.values() if u["user_id"] == user_id), None)

    async def update_profile(self, user_id, fields):
        for u in self.users.values():
            if u["user_id"] == user_id:
                u.update(fields)
                return dict(u)


@pytest.fixture
async def client(aiohttp_client):
    s = Settings(bot_token=BOT, jwt_secret="s" * 32, database_url="x")
    return await aiohttp_client(create_app(s, FakeRepo()))


async def login(client):
    r = await client.post("/api/auth/v1/telegram-login", json={"initData": make_init_data(BOT, USER)})
    assert r.status == 200
    return (await r.json())["token"]


async def test_login_then_me(client):
    token = await login(client)
    r = await client.get("/api/auth/v1/me", headers={"Authorization": f"Bearer {token}"})
    assert r.status == 200 and (await r.json())["user"]["telegram_id"] == 42


async def test_login_is_idempotent(client):
    await login(client)
    await login(client)
    assert len(client.app["user_repo"].users) == 1


async def test_bad_login_cases(client):
    assert (await client.post("/api/auth/v1/telegram-login", data="not json")).status == 400
    assert (await client.post("/api/auth/v1/telegram-login", json={})).status == 400
    assert (await client.post("/api/auth/v1/telegram-login", json={"initData": "hash=bad"})).status == 401


async def test_me_requires_valid_token(client):
    assert (await client.get("/api/auth/v1/me")).status == 401
    assert (await client.get("/api/auth/v1/me", headers={"Authorization": "Bearer junk"})).status == 401


async def test_patch_profile(client):
    h = {"Authorization": f"Bearer {await login(client)}"}
    r = await client.patch("/api/auth/v1/me", json={"timezone": "Europe/Warsaw", "language_code": "en"}, headers=h)
    assert r.status == 200 and (await r.json())["user"]["timezone"] == "Europe/Warsaw"
    assert (await client.patch("/api/auth/v1/me", json={"timezone": "Mars/Base"}, headers=h)).status == 400
    assert (await client.patch("/api/auth/v1/me", json={}, headers=h)).status == 400
