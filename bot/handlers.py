from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    await message.answer(
        "Привет! Я DevTeam Notifier Bot.\n"
        "Пока что я умею только /ping, но скоро начну слать уведомления о PR и CI."
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("pong 🏓")
