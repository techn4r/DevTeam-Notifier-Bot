import hashlib
import hmac
import json

from fastapi import APIRouter, Header, HTTPException, Request, status

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
        default=None, alias="X-Hub-Signature-256"
    ),
):
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
    repo_full_name = repo.get("full_name", None)

    if not repo_full_name:
        return

    if action == "opened":
        status_emoji = "🟦"
        status_text = "Открыт новый PR"
    elif action == "reopened":
        status_emoji = "🟩"
        status_text = "Переоткрыт PR"
    else:
        merged = pr.get("merged", False)
        if merged:
            status_emoji = "🟪"
            status_text = "PR влит (merged)"
        else:
            status_emoji = "🟥"
            status_text = "PR закрыт"

    text = (
        f"{status_emoji} {status_text}\n"
        f"📦 Репозиторий: <code>{repo_full_name}</code>\n"
        f"👤 Автор: <code>{user}</code>\n"
        f"🔀 {head_ref} → {base_ref}\n"
        f"📝 {title}\n"
    )

    if url:
        text += f"\n🔗 {url}"

    with SessionLocal() as db:
        chats = crud.get_chats_for_repo_full_name(db, repo_full_name)

    if not chats:
        return

    for chat in chats:
        await bot.send_message(
            chat_id=chat.telegram_chat_id,
            text=text,
            disable_web_page_preview=True,
        )
