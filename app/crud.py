from typing import List

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chat, Repo, Subscription


def get_or_create_chat(db: Session, telegram_chat_id: int, title: str | None = None) -> Chat:
    chat = db.execute(
        select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
    ).scalar_one_or_none()

    if chat:
        if title and chat.title != title:
            chat.title = title
            db.add(chat)
        return chat

    chat = Chat(
        telegram_chat_id=telegram_chat_id,
        title=title,
    )
    db.add(chat)
    db.commit()
    db.refresh(chat)
    return chat


def get_or_create_repo(db: Session, full_name: str) -> Repo:
    full_name = full_name.strip()
    repo = db.execute(
        select(Repo).where(Repo.full_name == full_name)
    ).scalar_one_or_none()

    if repo:
        return repo

    owner = None
    name = None
    if "/" in full_name:
        owner, name = full_name.split("/", 1)

    repo = Repo(
        provider="github",
        owner=owner,
        name=name,
        full_name=full_name,
    )
    db.add(repo)
    db.commit()
    db.refresh(repo)
    return repo


def subscribe_chat_to_repo(db: Session, chat: Chat, repo: Repo) -> Subscription:
    sub = db.execute(
        select(Subscription).where(
            Subscription.chat_id == chat.id,
            Subscription.repo_id == repo.id,
        )
    ).scalar_one_or_none()

    if sub:
        if not sub.is_active:
            sub.is_active = True
            db.add(sub)
            db.commit()
            db.refresh(sub)
        return sub

    sub = Subscription(
        chat_id=chat.id,
        repo_id=repo.id,
        is_active=True,
    )
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return sub


def get_chats_for_repo_full_name(db: Session, full_name: str) -> List[Chat]:
    repo = db.execute(
        select(Repo).where(Repo.full_name == full_name)
    ).scalar_one_or_none()

    if not repo:
        return []

    subs = db.execute(
        select(Subscription).where(
            Subscription.repo_id == repo.id,
            Subscription.is_active.is_(True),
        )
    ).scalars().all()

    chats = [sub.chat for sub in subs]
    print(
        "DEBUG: chats for repo",
        full_name,
        "->",
        [(c.id, c.telegram_chat_id, c.title) for c in chats]
    )
    return chats


def get_subscriptions_for_chat(db: Session, chat: Chat) -> list[Subscription]:
    subs = db.execute(
        select(Subscription).where(
            Subscription.chat_id == chat.id,
            Subscription.is_active.is_(True),
        )
    ).scalars().all()
    return subs


def unsubscribe_chat_from_repo(db: Session, chat: Chat, full_name: str) -> bool:
    full_name = full_name.strip()
    repo = db.execute(
        select(Repo).where(Repo.full_name == full_name)
    ).scalar_one_or_none()

    if not repo:
        return False

    sub = db.execute(
        select(Subscription).where(
            Subscription.chat_id == chat.id,
            Subscription.repo_id == repo.id,
        )
    ).scalar_one_or_none()

    if not sub or not sub.is_active:
        return False

    sub.is_active = False
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return True
