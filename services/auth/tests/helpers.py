import hashlib
import hmac
import json
import time
from urllib.parse import urlencode


def make_init_data(bot_token: str, user: dict, auth_date: int | None = None) -> str:
    """Генерує валідний initData так само, як це робить Telegram (для тестів)."""
    params = {
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        "query_id": "AAHtest",
        "user": json.dumps(user, separators=(",", ":"), ensure_ascii=False),
    }
    dcs = "\n".join(f"{k}={v}" for k, v in sorted(params.items()))
    secret = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    params["hash"] = hmac.new(secret, dcs.encode(), hashlib.sha256).hexdigest()
    return urlencode(params)
