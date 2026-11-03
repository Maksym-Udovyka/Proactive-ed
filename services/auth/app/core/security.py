import hashlib
import hmac
import json
import time
from datetime import datetime, timedelta, timezone
from urllib.parse import parse_qsl

import jwt


class InvalidInitData(Exception):
    """initData не пройшла перевірку. reason: коротка причина для логів."""

    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


def verify_telegram_init_data(init_data: str, bot_token: str, max_age_seconds: int = 86400,
                              now: float | None = None) -> dict:
    """Перевіряє підпис initData (HMAC-SHA256 за токеном бота) та її свіжість.

    Повертає словник користувача Telegram або кидає InvalidInitData.
    Поле `signature` (Ed25519) входить у data_check_string, тому не видаляється.
    """
    try:
        parsed = dict(parse_qsl(init_data, keep_blank_values=True))
    except Exception:
        raise InvalidInitData("malformed")

    received_hash = parsed.pop("hash", None)
    if not received_hash:
        raise InvalidInitData("no_hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    calculated = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(calculated, received_hash):
        raise InvalidInitData("bad_signature")

    try:
        auth_date = int(parsed["auth_date"])
    except (KeyError, ValueError):
        raise InvalidInitData("no_auth_date")
    current = now if now is not None else time.time()
    if current - auth_date > max_age_seconds:
        raise InvalidInitData("expired")
    if auth_date - current > 60:
        raise InvalidInitData("auth_date_in_future")

    try:
        user = json.loads(parsed.get("user", ""))
    except ValueError:
        raise InvalidInitData("no_user")
    if not isinstance(user, dict) or not isinstance(user.get("id"), int):
        raise InvalidInitData("no_user")
    return user


def create_jwt_token(user_id: int, telegram_id: int, secret_key: str, ttl_seconds: int = 86400) -> str:
    now = datetime.now(timezone.utc)
    payload = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "iat": now,
        "exp": now + timedelta(seconds=ttl_seconds),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_jwt_token(token: str, secret_key: str) -> dict | None:
    try:
        return jwt.decode(token, secret_key, algorithms=["HS256"], options={"require": ["exp", "sub"]})
    except jwt.PyJWTError:
        return None
