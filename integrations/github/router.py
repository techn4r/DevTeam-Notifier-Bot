import hashlib
import hmac
import json
from typing import Any

from fastapi import APIRouter, Header, HTTPException, Request, status
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from app.bot_instance import bot
from app.config import GITHUB_WEBHOOK_SECRET
from app.db import SessionLocal
from app import crud

router = APIRouter(prefix="/webhook/github", tags=["github"])


def verify_signature(signature_header: str | None, body: bytes) -> None:
    if not GITHUB_WEBHOOK_SECRET:
        return

    if not signature_header:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Missing X-Hub-Signature-256",
        )

    secret = GITHUB_WEBHOOK_SECRET.encode("utf-8")
    expected = "sha256=" + hmac.new(secret, body, hashlib.sha256).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid signature",
        )


@router.post("")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="X-GitHub-Event"),
    x_hub_signature_256: str | None = Header(
        default=None,
        alias="X-Hub-Signature-256",
    ),
) -> dict[str, Any]:
    raw_body = await request.body()

    verify_signature(x_hub_signature_256, raw_body)

    try:
        payload = json.loads(raw_body.decode("utf-8"))
    except json.JSONDecodeError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid JSON",
        )

    if x_github_event == "pull_request":
        await handle_pull_request_event(payload)
    elif x_github_event == "push":
        await handle_push_event(payload)
    elif x_github_event == "workflow_run":
        await handle_workflow_run_event(payload)

    return {"ok": True}


async def handle_pull_request_event(payload: dict) -> None:
    action = payload.get("action")
    pr = payload.get("pull_request") or {}
    repo = payload.get("repository") or {}

    if action not in {"opened", "closed", "reopened"}:
        return

    title = pr.get("title", "(no title)")
    url = pr.get("html_url", "")
    user = (pr.get("user") or {}).get("login", "unknown")
    base_ref = (pr.get("base") or {}).get("ref", "?")
    head_ref = (pr.get("head") or {}).get("ref", "?")
    pr_number = pr.get("number")
    repo_full_name = repo.get("full_name")
    if not repo_full_name:
        return

    if action == "opened":
        status_emoji = "🟦"
        status_text = "Открыт новый PR"
        action_subtype = "opened"
    elif action == "reopened":
        status_emoji = "🟩"
        status_text = "Переоткрыт PR"
        action_subtype = "reopened"
    else:
        merged = pr.get("merged", False)
        if merged:
            status_emoji = "🟪"
            status_text = "PR влит (merged)"
            action_subtype = "merged"
        else:
            status_emoji = "🟥"
            status_text = "PR закрыт"
            action_subtype = "closed"

    text = (
        f"{status_emoji} <b>{status_text}</b>\n"
        f"📦 Репозиторий: <code>{repo_full_name}</code>\n"
        f"👤 Автор: <code>{user}</code>\n"
        f"🔀 {head_ref} → {base_ref}\n"
        f"📝 {title}\n"
    )

    if url:
        text += f"\n🔗 {url}"

    buttons: list[InlineKeyboardButton] = []
    if url:
        buttons.append(
            InlineKeyboardButton(
                text="🔍 Открыть PR",
                url=url,
            )
        )

    if repo_full_name:
        repo_url = f"https://github.com/{repo_full_name}"
        buttons.append(
            InlineKeyboardButton(
                text="📦 Репозиторий",
                url=repo_url,
            )
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[buttons] if buttons else []
    )

    branch = base_ref or ""

    targets: list[dict[str, int]] = []

    with SessionLocal() as db:
        subs = crud.get_subscriptions_for_repo_full_name(db, repo_full_name)

        for sub in subs:
            if not crud.branch_matches(branch, sub.branches):
                continue

            chat = sub.chat
            repo_obj = sub.repo

            targets.append(
                {
                    "chat_tg_id": chat.telegram_chat_id,
                    "chat_db_id": chat.id,
                    "repo_db_id": repo_obj.id,
                }
            )

            summary = f"PR {action_subtype}: {title}"
            crud.log_event(
                db,
                chat=chat,
                repo=repo_obj,
                event_type="pull_request",
                event_subtype=action_subtype,
                payload_summary=summary,
            )

    if not targets:
        return

    for t in targets:
        reply_to: int | None = None
        if pr_number is not None and action in {"reopened", "closed"}:
            with SessionLocal() as db:
                root_id = crud.get_pr_thread_root_message_id(
                    db,
                    chat_db_id=t["chat_db_id"],
                    repo_db_id=t["repo_db_id"],
                    pr_number=pr_number,
                )
            if root_id:
                reply_to = root_id

        msg = await bot.send_message(
            chat_id=t["chat_tg_id"],
            text=text,
            disable_web_page_preview=True,
            reply_markup=keyboard,
            reply_to_message_id=reply_to,
        )

        if pr_number is not None and action in {"opened", "reopened"} and not reply_to:
            with SessionLocal() as db:
                crud.save_pr_thread_for_ids(
                    db,
                    chat_db_id=t["chat_db_id"],
                    repo_db_id=t["repo_db_id"],
                    pr_number=pr_number,
                    root_message_id=msg.message_id,
                )


async def handle_push_event(payload: dict) -> None:
    repo = payload.get("repository") or {}
    repo_full_name = repo.get("full_name")
    if not repo_full_name:
        return

    ref = payload.get("ref", "")
    branch = ref.split("/", 2)[-1] if ref.startswith("refs/") else ref

    pusher = (payload.get("pusher") or {}).get("name", "unknown")
    forced = payload.get("forced", False)
    commits = payload.get("commits") or []
    commit_count = len(commits)

    commit_lines: list[str] = []
    for c in commits[:5]:
        sha = (c.get("id") or "")[:7]
        msg = (c.get("message") or "").split("\n", 1)[0]
        author = (c.get("author") or {}).get("name", "unknown")
        commit_lines.append(f"- <code>{sha}</code> {msg} ({author})")

    if commit_count == 0:
        summary_text = "без новых коммитов 🤔"
    elif commit_count == 1:
        summary_text = "1 новый коммит"
    else:
        summary_text = f"{commit_count} новых коммитов"

    text = (
        "📤 <b>Push в репозиторий</b>\n"
        f"📦 <code>{repo_full_name}</code>\n"
        f"🌿 Ветка: <code>{branch}</code>\n"
        f"👤 Pusher: <code>{pusher}</code>\n"
        f"📊 {summary_text}\n"
    )

    if forced:
        text += "⚠️ Force push\n"

    if commit_lines:
        text += "\n" + "\n".join(commit_lines)

    buttons: list[InlineKeyboardButton] = []
    if repo_full_name:
        repo_url = f"https://github.com/{repo_full_name}"
        buttons.append(
            InlineKeyboardButton(
                text="📦 Репозиторий",
                url=repo_url,
            )
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[buttons] if buttons else []
    )

    targets: list[dict[str, int]] = []

    with SessionLocal() as db:
        subs = crud.get_subscriptions_for_repo_full_name(db, repo_full_name)

        for sub in subs:
            if not crud.branch_matches(branch, sub.branches):
                continue

            chat = sub.chat
            repo_obj = sub.repo

            targets.append(
                {
                    "chat_tg_id": chat.telegram_chat_id,
                    "chat_db_id": chat.id,
                    "repo_db_id": repo_obj.id,
                }
            )

            summary = f"push {branch}: {summary_text}"
            crud.log_event(
                db,
                chat=chat,
                repo=repo_obj,
                event_type="push",
                event_subtype=branch,
                payload_summary=summary,
            )

    if not targets:
        return

    for t in targets:
        await bot.send_message(
            chat_id=t["chat_tg_id"],
            text=text,
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )


async def handle_workflow_run_event(payload: dict) -> None:
    repo = payload.get("repository") or {}
    repo_full_name = repo.get("full_name")
    if not repo_full_name:
        return

    workflow_run = payload.get("workflow_run") or {}
    name = workflow_run.get("name", "Workflow")
    status = workflow_run.get("status", "unknown")
    conclusion = workflow_run.get("conclusion")
    url = workflow_run.get("html_url", "")
    branch = workflow_run.get("head_branch", "?")
    head_commit = workflow_run.get("head_commit") or {}
    sha = (head_commit.get("id") or "")[:7]
    message = (head_commit.get("message") or "").split("\n", 1)[0]
    author = (head_commit.get("author") or {}).get("name", "unknown")

    if status != "completed":
        emoji = "⏳"
        status_text = status
        subtype = status
    else:
        if conclusion == "success":
            emoji = "✅"
        elif conclusion in {"failure", "timed_out", "cancelled"}:
            emoji = "❌"
        else:
            emoji = "❔"
        status_text = conclusion or "completed"
        subtype = conclusion or "completed"

    text = (
        f"{emoji} <b>GitHub Actions: {name}</b>\n"
        f"📦 <code>{repo_full_name}</code>\n"
        f"🌿 Ветка: <code>{branch}</code>\n"
        f"📌 Статус: <code>{status_text}</code>\n"
        f"👤 Commit: <code>{sha}</code> — {message} ({author})\n"
    )

    if url:
        text += f"\n🔗 {url}"

    buttons: list[InlineKeyboardButton] = []
    if url:
        buttons.append(
            InlineKeyboardButton(
                text="🚀 Открыть run",
                url=url,
            )
        )
    if repo_full_name:
        repo_url = f"https://github.com/{repo_full_name}"
        buttons.append(
            InlineKeyboardButton(
                text="📦 Репозиторий",
                url=repo_url,
            )
        )

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[buttons] if buttons else []
    )

    targets: list[dict[str, int]] = []

    with SessionLocal() as db:
        subs = crud.get_subscriptions_for_repo_full_name(db, repo_full_name)

        for sub in subs:
            if not crud.branch_matches(branch, sub.branches):
                continue

            chat = sub.chat
            repo_obj = sub.repo

            targets.append(
                {
                    "chat_tg_id": chat.telegram_chat_id,
                    "chat_db_id": chat.id,
                    "repo_db_id": repo_obj.id,
                }
            )

            summary = f"CI {name}: {status_text} ({branch})"
            crud.log_event(
                db,
                chat=chat,
                repo=repo_obj,
                event_type="workflow_run",
                event_subtype=subtype,
                payload_summary=summary,
            )

    if not targets:
        return

    for t in targets:
        await bot.send_message(
            chat_id=t["chat_tg_id"],
            text=text,
            disable_web_page_preview=True,
            reply_markup=keyboard,
        )
