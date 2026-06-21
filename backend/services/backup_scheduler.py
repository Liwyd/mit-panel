"""Background task that periodically sends a database backup to Telegram.

Reads settings on every tick so enabling/disabling and interval changes from
the UI take effect without a restart.
"""

import asyncio
import time

from backend.utils.logger import logger
from backend.utils.settings_store import get_settings
from backend.utils.telegram import send_backup_to_telegram


async def backup_scheduler():
    # Start the clock now so we don't fire immediately on every container boot.
    last_sent = time.time()
    while True:
        try:
            s = get_settings()
            enabled = (
                s.get("backup_enabled")
                and (s.get("telegram_bot_token") or "").strip()
                and (s.get("telegram_chat_id") or "").strip()
            )
            if enabled:
                interval = max(1, int(s.get("backup_interval_hours") or 6)) * 3600
                now = time.time()
                if now - last_sent >= interval:
                    ok, message = await send_backup_to_telegram(s)
                    logger.info(f"Scheduled Telegram backup: {message}")
                    last_sent = now
        except Exception as exc:
            logger.error(f"Backup scheduler error: {exc}")
        await asyncio.sleep(60)
