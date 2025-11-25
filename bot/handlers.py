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
        "Я могу присылать уведомления о GitHub событиях (PR, push, CI) в этот чат.\n\n"
        f"Твой chat_id: <code>{chat_id}</code>\n\n"
        "Подпиши чат на репозиторий командой:\n"
        "<code>/link_repo owner/repo</code>\n"
        "Например:\n"
        "<code>/link_repo example/repo</code>\n\n"
        "Посмотреть текущие подписки: <code>/subscriptions</code>\n"
        "Настроить фильтр по веткам: <code>/set_branches owner/repo main,develop</code>\n"
        "Дайджест событий за сутки: <code>/daily_digest</code>"
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
        "Теперь события из этого репозитория будут приходить сюда."
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
                branch_filter = sub.branches or "все ветки"
                lines.append(
                    f"• <code>{repo.full_name}</code> "
                    f"(ветки: <code>{branch_filter}</code>)"
                )
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


@router.message(Command("set_branches"))
async def cmd_set_branches(message: Message):
    parts = message.text.split(maxsplit=2)
    if len(parts) < 3:
        await message.answer(
            "Использование:\n"
            "<code>/set_branches owner/repo main,develop,release/*</code>"
        )
        return

    full_name = parts[1].strip()
    branches_str = parts[2].strip()

    if "/" not in full_name:
        await message.answer(
            "Некорректный формат репозитория, ожидаю <code>owner/repo</code>."
        )
        return

    chat_id = message.chat.id
    title = message.chat.title or message.chat.full_name or message.chat.username

    with SessionLocal() as db:
        chat = crud.get_or_create_chat(db, telegram_chat_id=chat_id, title=title)
        ok = crud.set_branches_for_subscription(db, chat, full_name, branches_str)

    if not ok:
        await message.answer(
            "Не нашёл подписки на этот репозиторий.\n"
            f"Сначала подпишись: <code>/link_repo {full_name}</code>"
        )
        return

    await message.answer(
        f"✅ Для <code>{full_name}</code> установлен фильтр по веткам:\n"
        f"<code>{branches_str}</code>\n\n"
        "Поддерживаются точные имена и шаблоны с <code>/*</code>, например:\n"
        "<code>main,develop,release/*</code>"
    )


@router.message(Command("daily_digest"))
async def cmd_daily_digest(message: Message):
    parts = message.text.split(maxsplit=1)
    hours = 24
    if len(parts) == 2:
        arg = parts[1].strip()
        if arg.endswith("d") and arg[:-1].isdigit():
            hours = int(arg[:-1]) * 24
        elif arg.isdigit():
            hours = int(arg)

    chat_id = message.chat.id
    title = message.chat.title or message.chat.full_name or message.chat.username

    with SessionLocal() as db:
        chat = crud.get_or_create_chat(db, telegram_chat_id=chat_id, title=title)
        summaries = crud.get_daily_digest_for_chat_summaries(db, chat, hours=hours)

    if not summaries:
        await message.answer(f"За последние {hours} часов событий не было 🌿")
        return

    lines: list[str] = []
    lines.append(f"📊 Дайджест за последние {hours} ч:")

    for item in summaries:
        ts = item["timestamp"].strftime("%Y-%m-%d %H:%M")
        repo_name = item["repo_full_name"]
        et = item["event_type"]
        st = item["event_subtype"] or ""
        summary = item["payload_summary"] or ""
        lines.append(
            f"• [{ts}] <code>{repo_name}</code> — {et}/{st}: {summary}"
        )

    text = "\n".join(lines)
    await message.answer(text)
