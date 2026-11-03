import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    bot_token: str
    jwt_secret: str
    database_url: str
    port: int = 8001
    jwt_ttl_seconds: int = 86400
    init_data_max_age_seconds: int = 86400

    @classmethod
    def from_env(cls) -> "Settings":
        missing = [k for k in ("BOT_TOKEN", "JWT_SECRET", "DATABASE_URL") if not os.getenv(k)]
        if missing:
            raise RuntimeError(f"Не задано змінні середовища: {', '.join(missing)}")
        settings = cls(
            bot_token=os.environ["BOT_TOKEN"],
            jwt_secret=os.environ["JWT_SECRET"],
            database_url=os.environ["DATABASE_URL"],
            port=int(os.getenv("PORT", "8001")),
            jwt_ttl_seconds=int(os.getenv("JWT_TTL_SECONDS", "86400")),
            init_data_max_age_seconds=int(os.getenv("INIT_DATA_MAX_AGE_SECONDS", "86400")),
        )
        if len(settings.jwt_secret) < 32:
            raise RuntimeError("JWT_SECRET має містити щонайменше 32 символи")
        return settings
