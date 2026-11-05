import json

import jwt
from aiohttp import web

from app.core.config import get_settings

API_PREFIX = "/api/planning/v1"
PUBLIC_PATHS = {f"{API_PREFIX}/health"}


def _unauthorized(message: str) -> web.HTTPUnauthorized:
    return web.HTTPUnauthorized(
        text=json.dumps({"error": message}),
        content_type="application/json",
    )


def decode_token(token: str) -> dict:
    settings = get_settings()
    return jwt.decode(
        token, settings.jwt_secret, algorithms=[settings.jwt_algorithm]
    )


@web.middleware
async def auth_middleware(request: web.Request, handler):
    if request.path in PUBLIC_PATHS:
        return await handler(request)

    scheme, _, token = request.headers.get("Authorization", "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise _unauthorized("Missing bearer token")

    try:
        claims = decode_token(token)
    except jwt.ExpiredSignatureError:
        raise _unauthorized("Token expired")
    except jwt.InvalidTokenError:
        raise _unauthorized("Invalid token")

    raw_user_id = claims.get("sub", claims.get("user_id"))
    try:
        request["user_id"] = int(raw_user_id)
    except (TypeError, ValueError):
        raise _unauthorized("Token has no valid user id")

    return await handler(request)