"""Send the panel database as a backup document to a Telegram chat."""

import os
import datetime

import httpx

from backend.utils.settings_store import get_settings

DB_PATH = os.path.join(os.environ.get("MITPANEL_DATA_DIR", "/app/data"), "mitpanel.db")


async def send_backup_to_telegram(settings: dict | None = None):
    """Returns (ok: bool, message: str)."""
    s = settings or get_settings()
    token = (s.get("telegram_bot_token") or "").strip()
    chat_id = (s.get("telegram_chat_id") or "").strip()

    if not token or not chat_id:
        return False, "Telegram bot token or chat id is not set"
    if not os.path.exists(DB_PATH):
        return False, "Database file not found"

    stamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    url = f"https://api.telegram.org/bot{token}/sendDocument"
    try:
        with open(DB_PATH, "rb") as db_file:
            files = {
                "document": (f"mitpanel-{stamp}.db", db_file, "application/octet-stream")
            }
            data = {
                "chat_id": chat_id,
                "caption": f"\U0001f433 MIT Panel backup — {stamp}",
            }
            async with httpx.AsyncClient(timeout=120) as client:
                resp = await client.post(url, data=data, files=files)

        if resp.status_code == 200 and resp.json().get("ok"):
            return True, "Backup sent to Telegram"
        return False, f"Telegram API error ({resp.status_code}): {resp.text[:200]}"
    except Exception as exc:
        return False, f"Failed to send backup: {exc}"
