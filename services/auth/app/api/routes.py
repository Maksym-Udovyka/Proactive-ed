import logging
import re
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from aiohttp import web

from app.core.security import (InvalidInitData, create_jwt_token, decode_jwt_token,
                               verify_telegram_init_data)

log = logging.getLogger("auth")
routes = web.RouteTableDef()
_LANG_RE = re.compile(r"^[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})?$")


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


async def _json_body(request: web.Request) -> dict:
    try:
        data = await request.json()
    except Exception:
        raise ApiError(400, "Request body must be valid JSON")
    if not isinstance(data, dict):
        raise ApiError(400, "Request body must be a JSON object")
    return data


def _current_user_id(request: web.Request) -> int:
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
    user = await request.app["user_repo"].get_user_by_id(_current_user_id(request))
    if not user:
        raise ApiError(401, "User no longer exists")
    return web.json_response({"user": user})


@routes.patch("/api/auth/v1/me")
async def update_me(request: web.Request):
    """Редагування профілю: first_name, language_code, timezone."""
    user_id = _current_user_id(request)
    data = await _json_body(request)
    fields: dict = {}

    if "first_name" in data:
        v = data["first_name"]
        if not isinstance(v, str) or not 1 <= len(v.strip()) <= 64:
            raise ApiError(400, "first_name must be a string of 1-64 characters")
        fields["first_name"] = v.strip()
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
