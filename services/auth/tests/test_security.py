import time

import pytest

from app.core.security import (InvalidInitData, create_jwt_token, decode_jwt_token,
                               verify_telegram_init_data)
from tests.helpers import make_init_data

BOT = "123456:TEST-TOKEN"
USER = {"id": 42, "first_name": "Іван", "username": "ivan", "language_code": "uk"}


def test_valid_init_data():
    assert verify_telegram_init_data(make_init_data(BOT, USER), BOT)["id"] == 42


def test_wrong_bot_token_rejected():
    with pytest.raises(InvalidInitData):
        verify_telegram_init_data(make_init_data("999:OTHER", USER), BOT)


def test_tampered_user_rejected():
    data = make_init_data(BOT, USER).replace("42", "43")
    with pytest.raises(InvalidInitData):
        verify_telegram_init_data(data, BOT)


def test_expired_rejected():
    old = int(time.time()) - 7 * 86400
    with pytest.raises(InvalidInitData) as e:
        verify_telegram_init_data(make_init_data(BOT, USER, auth_date=old), BOT)
    assert e.value.reason == "expired"


def test_missing_hash_rejected():
    with pytest.raises(InvalidInitData):
        verify_telegram_init_data("auth_date=1&user=%7B%7D", BOT)


def test_jwt_roundtrip_and_tamper():
    t = create_jwt_token(7, 42, "s" * 32)
    assert decode_jwt_token(t, "s" * 32)["sub"] == "7"
    assert decode_jwt_token(t, "x" * 32) is None
    assert decode_jwt_token(create_jwt_token(7, 42, "s" * 32, ttl_seconds=-5), "s" * 32) is None
