import asyncio

import uvicorn
from fastapi import FastAPI

from app.config import APP_HOST, APP_PORT
from app.bot_instance import bot, dp
from app.db import init_db
from bot.handlers import router as bot_router
from integrations.github.router import router as github_router


def create_fastapi_app() -> FastAPI:
    app = FastAPI(title="DevTeam Notifier API")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    app.include_router(github_router)

    return app


async def run_bot():
    dp.include_router(bot_router)
    await dp.start_polling(bot)


async def run_api():
    app = create_fastapi_app()
    config = uvicorn.Config(app, host=APP_HOST, port=APP_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def async_main():
    await asyncio.gather(
        run_bot(),
        run_api(),
    )


if __name__ == "__main__":
    init_db()
    asyncio.run(async_main())
