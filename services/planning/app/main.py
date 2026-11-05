import logging

import asyncpg
from aiohttp import web

from app.api.routes import setup_routes
from app.core.config import get_settings
from app.core.security import auth_middleware

logger = logging.getLogger("planning")


async def db_pool_ctx(app: web.Application):
    settings = get_settings()
    app["db"] = await asyncpg.create_pool(
        settings.database_url, min_size=1, max_size=5
    )
    logger.info("Database pool created")
    yield
    await app["db"].close()
    logger.info("Database pool closed")


def create_app() -> web.Application:
    app = web.Application(middlewares=[auth_middleware])
    app.cleanup_ctx.append(db_pool_ctx)
    setup_routes(app)
    return app


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    settings = get_settings()
    web.run_app(create_app(), host=settings.host, port=settings.port)


if __name__ == "__main__":
    main()