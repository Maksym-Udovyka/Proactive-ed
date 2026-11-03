import os
import asyncpg
from aiohttp import web
from dotenv import load_dotenv

from app.api.routes import routes
from app.repository.user_repository import UserRepository

load_dotenv()

async def init_app():
    app = web.Application()
    
    # Инициализация пула подключений к PostgreSQL
    db_url = os.getenv('DATABASE_URL')
    app['db_pool'] = await asyncpg.create_pool(dsn=db_url)
    app['user_repo'] = UserRepository(app['db_pool'])
    
    app.add_routes(routes)
    
    async def cleanup(app):
        await app['db_pool'].close()
        
    app.on_cleanup.append(cleanup)
    return app

if __name__ == '__main__':
    port = int(os.getenv('PORT', 8001))
    web.run_app(init_app(), port=port)