import logging
import re
import unicodedata
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiohttp import web

from app.core.security import (InvalidInitData, create_jwt_token, decode_jwt_token,
                               verify_telegram_init_data)

log = logging.getLogger("auth")
routes = web.RouteTableDef()
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")

# Маршрути, доступні без токена. Усе інше захищене за замовчуванням (див. auth_middleware).
PUBLIC_PATHS = frozenset({
    "/api/auth/v1/health",
    "/api/auth/v1/telegram-login",
})

_DISPLAY_NAME_MAX = 64
_PUBLIC_IDS_MAX = 50
_BIGINT_MAX = 2 ** 63 - 1
# Невидимі символи та керування напрямком тексту: через них можна підробити чуже ім'я.
_FORBIDDEN_NAME_CHARS = frozenset(
    "​‎‏‪‫‬‭‮⁦⁧⁨⁩﻿")


class ApiError(Exception):
    def __init__(self, status: int, message: str):
        self.status, self.message = status, message


@web.middleware
async def error_middleware(request: web.Request, handler):
    try:
        return await handler(request)
    except ApiError as e:
        return web.json_response({"error": e.message}, status=e.status)
    except web.HTTPException:
        raise
    except Exception:
        log.exception("Unhandled error on %s %s", request.method, request.path)
        return web.json_response({"error": "Internal server error"}, status=500)


def _authenticate(request: web.Request) -> int:
    """Перевіряє заголовок Authorization: Bearer <JWT> і повертає user_id."""
    header = request.headers.get("Authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        raise ApiError(401, "Unauthorized")
    payload = decode_jwt_token(token.strip(), request.app["settings"].jwt_secret)
    if not payload:
        raise ApiError(401, "Invalid or expired token")
    try:
        return int(payload["sub"])
    except (KeyError, ValueError):
        raise ApiError(401, "Invalid token")


@web.middleware
async def auth_middleware(request: web.Request, handler):
    """Вимагає JWT на всіх маршрутах, крім PUBLIC_PATHS. user_id кладе в request["user_id"].

    Підключати у create_app ПІСЛЯ error_middleware: тоді ApiError з цього middleware
    перетворюється на JSON-відповідь у тому самому форматі.
    """
    if request.path not in PUBLIC_PATHS:
        request["user_id"] = _authenticate(request)
    return await handler(request)


async def _json_body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise ApiError(400, "Request body must be valid JSON")
    if not isinstance(data, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return data


def _clean_display_name(value) -> str | None:
    """Перевіряє відображуване ім'я. None або порожній рядок скидають його до імені з Telegram."""
    if value is None:
        return None
    if not isinstance(value, str):
        raise ApiError(400, "display_name must be a string")
    name = " ".join(value.split())  # прибирає переноси, табуляції та подвійні пробіли
    if not name:
        return None
    if len(name) > _DISPLAY_NAME_MAX:
        raise ApiError(400, f"display_name must be at most {_DISPLAY_NAME_MAX} characters")
    if any(unicodedata.category(c) == "Cc" or c in _FORBIDDEN_NAME_CHARS for c in name):
        raise ApiError(400, "display_name contains forbidden characters")
    return name


@routes.get("/api/auth/v1/health")
async def health(request: web.Request):
    return web.json_response({"status": "ok"})


@routes.post("/api/auth/v1/telegram-login")
async def telegram_login(request: web.Request):
    """Приймає initData Telegram Mini App, перевіряє підпис і видає JWT."""
    s = request.app["settings"]
    data = await _json_body(request)
    init_data = data.get("initData")
    if not isinstance(init_data, str) or not init_data:
        raise ApiError(400, "initData is required")

    try:
        tg_user = verify_telegram_init_data(init_data, s.bot_token, s.init_data_max_age_seconds)
    except InvalidInitData as e:
        log.warning("telegram-login rejected: %s", e.reason)
        raise ApiError(401, "Initdata expired, reopen the app" if e.reason == "expired"
                       else "Invalid Telegram signature")

    user = await request.app["user_repo"].upsert_telegram_user(
        telegram_id=tg_user["id"],
        first_name=(tg_user.get("first_name") or "")[:64],
        username=tg_user.get("username"),
        language_code=(tg_user.get("language_code") or "uk")[:10],
    )
    token = create_jwt_token(user["user_id"], user["telegram_id"], s.jwt_secret, s.jwt_ttl_seconds)
    log.info("login ok user_id=%s", user["user_id"])
    return web.json_response({"token": token, "expires_in": s.jwt_ttl_seconds, "user": user})


@routes.get("/api/auth/v1/me")
async def get_me(request: web.Request):
    user = await request.app["user_repo"].get_user_by_id(request["user_id"])
    if not user:
        raise ApiError(401, "User no longer exists")
    return web.json_response({"user": user})


@routes.patch("/api/auth/v1/me")
async def update_me(request: web.Request):
    """Редагування профілю: display_name, language_code, timezone.

    first_name не редагується: він синхронізується з Telegram при кожному вході.
    Власне ім'я користувача зберігається в display_name і вхід його не змінює.
    """
    user_id = request["user_id"]
    data = await _json_body(request)
    fields: dict = {}

    if "display_name" in data:
        fields["display_name"] = _clean_display_name(data["display_name"])
    if "language_code" in data:
        v = data["language_code"]
        if not isinstance(v, str) or not _LANG_RE.match(v):
            raise ApiError(400, "language_code is invalid")
        fields["language_code"] = v
    if "timezone" in data:
        v = data["timezone"]
        try:
            ZoneInfo(v)
        except (ZoneInfoNotFoundError, ValueError, TypeError, OSError):
            raise ApiError(400, "timezone must be a valid IANA name, e.g. Europe/Kyiv")
        fields["timezone"] = v
    if not fields:
        raise ApiError(400, "No updatable fields provided")

    user = await request.app["user_repo"].update_profile(user_id, fields)
    if not user:
        raise ApiError(401, "User no longer exists")
    return web.json_response({"user": user})


@routes.get("/api/auth/v1/users/public")
async def get_public_profiles(request: web.Request):
    """Публічні профілі за списком id: GET /users/public?ids=1,2,3.

    Повертає лише user_id та ім'я, яке бачать інші люди. Жодних telegram_id, username,
    часового поясу чи мови. Сервіс планування використовуватиме це для списку учасників.

    УВАГА: поки сервісу планування немає, будь-який авторизований користувач може
    дізнатися ім'я за user_id. Коли з'являться плани, обмежити відповідь учасниками
    спільних планів.
    """
    raw = request.query.get("ids", "")
    try:
        ids = sorted({int(x) for x in raw.split(",") if x.strip()})
    except ValueError:
        raise ApiError(400, "ids must be a comma-separated list of integers")
    if not ids:
        raise ApiError(400, "ids is required")
    if len(ids) > _PUBLIC_IDS_MAX:
        raise ApiError(400, f"At most {_PUBLIC_IDS_MAX} ids per request")
    if ids[0] < 1 or ids[-1] > _BIGINT_MAX:
        raise ApiError(400, "ids must be positive integers")

    users = await request.app["user_repo"].get_public_profiles(ids)
    return web.json_response({"users": users})
