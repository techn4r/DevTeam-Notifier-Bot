from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    chat_id = message.chat.id
    await message.answer(
        "Привет! Я DevTeam Notifier Bot.\n"
        "Пока что я умею /ping и принимаю вебхуки от GitHub.\n\n"
        f"Твой chat_id: {chat_id}\n"
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("pong 🏓")
