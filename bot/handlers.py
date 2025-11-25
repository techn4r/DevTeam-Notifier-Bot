from aiogram import Router
from aiogram.filters import CommandStart, Command
from aiogram.types import Message

from app.db import SessionLocal
from app import crud

router = Router()


@router.message(CommandStart())
async def cmd_start(message: Message):
    chat_id = message.chat.id
    title = message.chat.title or message.chat.full_name or message.chat.username

    with SessionLocal() as db:
        crud.get_or_create_chat(db, telegram_chat_id=chat_id, title=title)

    await message.answer(
        "Привет! Я DevTeam Notifier Bot.\n"
        "Я могу присылать уведомления о GitHub pull request'ах в этот чат.\n\n"
        f"Твой chat_id: <code>{chat_id}</code>\n\n"
        "Подпиши чат на репозиторий командой:\n"
        "<code>/link_repo owner/repo</code>\n"
        "Например:\n"
        "<code>/link_repo example/repo</code>\n\n"
        "Посмотреть текущие подписки: <code>/subscriptions</code>"
    )


@router.message(Command("ping"))
async def cmd_ping(message: Message):
    await message.answer("pong 🏓")


@router.message(Command("link_repo"))
async def cmd_link_repo(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Нужно указать репозиторий в формате <code>owner/repo</code>.\n"
            "Пример: <code>/link_repo example/repo</code>"
        )
        return

    full_name = parts[1].strip()
    if "/" not in full_name:
        await message.answer(
            "Некорректный формат. Ожидалось <code>owner/repo</code>.\n"
            "Пример: <code>/link_repo example/repo</code>"
        )
        return

    chat_id = message.chat.id
    title = message.chat.title or message.chat.full_name or message.chat.username

    with SessionLocal() as db:
        chat = crud.get_or_create_chat(db, telegram_chat_id=chat_id, title=title)
        repo = crud.get_or_create_repo(db, full_name=full_name)
        crud.subscribe_chat_to_repo(db, chat, repo)

    await message.answer(
        f"✅ Чат подписан на репозиторий <code>{full_name}</code>.\n"
        "Теперь события pull request из этого репозитория будут приходить сюда."
    )


@router.message(Command("subscriptions"))
async def cmd_subscriptions(message: Message):
    chat_id = message.chat.id
    title = message.chat.title or message.chat.full_name or message.chat.username

    with SessionLocal() as db:
        chat = crud.get_or_create_chat(db, telegram_chat_id=chat_id, title=title)
        subs = crud.get_subscriptions_for_chat(db, chat)

        if not subs:
            text = "❌ Для этого чата пока нет активных подписок на репозитории."
        else:
            lines = ["📦 Активные подписки этого чата:"]
            for sub in subs:
                repo = sub.repo
                lines.append(f"• <code>{repo.full_name}</code>")
            text = "\n".join(lines)

    await message.answer(text)


@router.message(Command("unlink_repo"))
async def cmd_unlink_repo(message: Message):
    parts = message.text.split(maxsplit=1)
    if len(parts) < 2:
        await message.answer(
            "Нужно указать репозиторий в формате <code>owner/repo</code>.\n"
            "Пример: <code>/unlink_repo example/repo</code>"
        )
        return

    full_name = parts[1].strip()
    if "/" not in full_name:
        await message.answer(
            "Некорректный формат. Ожидалось <code>owner/repo</code>.\n"
            "Пример: <code>/unlink_repo example/repo</code>"
        )
        return

    chat_id = message.chat.id
    title = message.chat.title or message.chat.full_name or message.chat.username

    with SessionLocal() as db:
        chat = crud.get_or_create_chat(db, telegram_chat_id=chat_id, title=title)
        ok = crud.unsubscribe_chat_from_repo(db, chat, full_name=full_name)

    if ok:
        await message.answer(
            f"✅ Подписка на репозиторий <code>{full_name}</code> отключена для этого чата."
        )
    else:
        await message.answer(
            f"Не нашёл активной подписки на <code>{full_name}</code> для этого чата."
        )
