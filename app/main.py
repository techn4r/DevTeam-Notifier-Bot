import asyncio

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
import uvicorn

from app.config import TELEGRAM_BOT_TOKEN, APP_HOST, APP_PORT
from bot.handlers import router as bot_router


def create_fastapi_app() -> FastAPI:
    app = FastAPI(title="DevTeam Notifier API")

    @app.get("/health")
    async def health():
        return {"status": "ok"}

    return app


async def run_bot():
    bot = Bot(token=TELEGRAM_BOT_TOKEN)
    dp = Dispatcher()
    dp.include_router(bot_router)

    await dp.start_polling(bot)


async def run_api():
    app = create_fastapi_app()
    config = uvicorn.Config(app, host=APP_HOST, port=APP_PORT, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()


async def main():
    await asyncio.gather(
        run_bot(),
        run_api(),
    )


if __name__ == "__main__":
    asyncio.run(main())
