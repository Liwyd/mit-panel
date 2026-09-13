"""Daily backup delivery, at midnight Tehran time.

The archive is sent to every superadmin over Telegram, which doubles as
off-server storage: if the VPS is lost entirely, the backups are still sitting
in the chat history.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
from datetime import datetime
from zoneinfo import ZoneInfo

from aiogram import Bot
from aiogram.types import FSInputFile

from backend.bot import texts
from backend.bot import db
from backend.bot.backup import create_backup
from backend.bot.config import bot_config as settings

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")


async def send_backup(bot: Bot, targets: list[int] | None = None) -> bool:
    """Build the archive and push it to the superadmins. Returns True on success."""
    now = datetime.now(TEHRAN)
    try:
        archive_path, media_included = create_backup(now.strftime("%Y%m%d-%H%M%S"))
    except Exception as exc:
        logger.error(f"backup creation failed: {exc}")
        return False

    size_mb = os.path.getsize(archive_path) / (1024 * 1024)
    caption = texts.BACKUP_CAPTION.format(
        date=now.strftime("%Y-%m-%d %H:%M"),
        size=size_mb,
        media=texts.BACKUP_WITH_MEDIA if media_included else texts.BACKUP_WITHOUT_MEDIA,
    )

    ok = False
    try:
        for chat_id in targets or settings.superadmin_id_list:
            try:
                await bot.send_document(
                    chat_id, document=FSInputFile(archive_path), caption=caption
                )
                ok = True
            except Exception as exc:
                logger.error(f"failed sending backup to {chat_id}: {exc}")
    finally:
        # The archive lives in its own temp directory; drop the whole thing.
        shutil.rmtree(os.path.dirname(archive_path), ignore_errors=True)
    return ok


async def tick(bot: Bot) -> None:
    now = datetime.now(TEHRAN)
    if now.hour != settings.backup_hour:
        return
    stamp = now.strftime("%Y-%m-%d")
    if db.get_setting("last_backup_date") == stamp:
        return
    if await send_backup(bot):
        db.set_setting("last_backup_date", stamp)
        logger.info(f"daily backup sent for {stamp}")


async def run_backup_scheduler(bot: Bot) -> None:
    while True:
        try:
            await tick(bot)
        except Exception as exc:  # one bad night must not stop tomorrow's backup
            logger.error(f"backup scheduler failed: {exc}")
        await asyncio.sleep(600)
