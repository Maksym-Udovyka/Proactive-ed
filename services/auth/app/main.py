import logging
import os

import asyncpg
from aiohttp import web
from dotenv import load_dotenv

from app.api.routes import error_middleware, routes
from app.core.config import Settings
from app.repository.user_repository import UserRepository


def create_app(settings: Settings, user_repo=None) -> web.Application:
    """user_repo можна підставити в тестах; інакше створюється пул PostgreSQL."""
    app = web.Application(middlewares=[error_middleware], client_max_size=64 * 1024)
    app["settings"] = settings
    if user_repo is not None:
        app["user_repo"] = user_repo
    else:
        async def init_db(app: web.Application):
            pool = await asyncpg.create_pool(dsn=settings.database_url, min_size=1, max_size=10)
            app["db_pool"] = pool
            app["user_repo"] = UserRepository(pool)
            yield
            await pool.close()

        app.cleanup_ctx.append(init_db)
    app.add_routes(routes)
    return app


def main():
    load_dotenv()
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    settings = Settings.from_env()
    web.run_app(create_app(settings), host="0.0.0.0", port=settings.port)


if __name__ == "__main__":
    main()
