from datetime import datetime, timedelta, timezone
from typing import List, Dict, Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Chat, Repo, Subscription, EventLog, PRThread


def get_or_create_chat(db: Session, telegram_chat_id: int, title: str | None = None) -> Chat:
    chat = db.execute(
        select(Chat).where(Chat.telegram_chat_id == telegram_chat_id)
    ).scalar_one_or_none()

    if chat:
        if title and chat.title != title:
            chat.title = title
            db.add(chat)
            db.commit()
            db.refresh(chat)
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


def get_subscriptions_for_repo_full_name(db: Session, full_name: str) -> list[Subscription]:
    full_name = full_name.strip()
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
    return subs


def set_branches_for_subscription(
    db: Session,
    chat: Chat,
    full_name: str,
    branches: str,
) -> bool:
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

    if not sub:
        return False

    sub.branches = branches.strip()
    db.add(sub)
    db.commit()
    db.refresh(sub)
    return True

def branch_matches(branch: str, branches_filter: str | None) -> bool:
    if not branches_filter:
        return True

    branch = branch.strip()
    patterns = [p.strip() for p in branches_filter.split(",") if p.strip()]

    if not patterns:
        return True

    for pattern in patterns:
        if pattern.endswith("/*"):
            prefix = pattern[:-2]
            if branch.startswith(prefix + "/"):
                return True
        else:
            if branch == pattern:
                return True

    return False


def log_event(
    db: Session,
    *,
    chat: Chat,
    repo: Repo,
    event_type: str,
    event_subtype: str | None,
    payload_summary: str | None,
    ts: datetime | None = None,
) -> None:
    if ts is None:
        ts = datetime.now(timezone.utc)

    log = EventLog(
        chat_id=chat.id,
        repo_id=repo.id,
        event_type=event_type,
        event_subtype=event_subtype,
        timestamp=ts,
        payload_summary=payload_summary,
    )
    db.add(log)
    db.commit()


def get_daily_digest_for_chat_summaries(
    db: Session,
    chat: Chat,
    hours: int = 24,
) -> list[Dict[str, Any]]:
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    stmt = (
        select(
            EventLog.timestamp,
            EventLog.event_type,
            EventLog.event_subtype,
            EventLog.payload_summary,
            Repo.full_name,
        )
        .join(Repo, EventLog.repo_id == Repo.id)
        .where(
            EventLog.chat_id == chat.id,
            EventLog.timestamp >= since,
        )
        .order_by(EventLog.timestamp.asc())
    )

    rows = db.execute(stmt).all()

    result: list[Dict[str, Any]] = []
    for ts, event_type, event_subtype, payload_summary, full_name in rows:
        result.append(
            {
                "timestamp": ts,
                "event_type": event_type,
                "event_subtype": event_subtype,
                "payload_summary": payload_summary,
                "repo_full_name": full_name,
            }
        )

    return result


def save_pr_thread_for_ids(
    db: Session,
    chat_db_id: int,
    repo_db_id: int,
    pr_number: int,
    root_message_id: int,
) -> None:
    thread = db.execute(
        select(PRThread).where(
            PRThread.chat_id == chat_db_id,
            PRThread.repo_id == repo_db_id,
            PRThread.pr_number == pr_number,
        )
    ).scalar_one_or_none()

    if thread:
        thread.root_message_id = root_message_id
        db.add(thread)
    else:
        thread = PRThread(
            chat_id=chat_db_id,
            repo_id=repo_db_id,
            pr_number=pr_number,
            root_message_id=root_message_id,
        )
        db.add(thread)

    db.commit()


def get_pr_thread_root_message_id(
    db: Session,
    chat_db_id: int,
    repo_db_id: int,
    pr_number: int,
) -> int | None:
    thread = db.execute(
        select(PRThread).where(
            PRThread.chat_id == chat_db_id,
            PRThread.repo_id == repo_db_id,
            PRThread.pr_number == pr_number,
        )
    ).scalar_one_or_none()

    if not thread:
        return None
    return thread.root_message_id
