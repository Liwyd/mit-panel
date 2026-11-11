"""Superadmin receipt delivery — how a pending request becomes reviewable.

A request that is never announced is a customer waiting for nothing: the row
sits in SQLite while everyone assumes someone else is reviewing it. Delivery
is therefore treated like the money move itself: every failed attempt is
logged, a transient failure gets one retry, and a receipt that reaches nobody
is logged as critical so the ops log names exactly which request needs a human
(the manual «درخواست‌های باز» list and the daily digest stay as backstops).
"""

from __future__ import annotations

import asyncio
import logging

from aiogram import Bot

from backend.bot.config import bot_config as settings

logger = logging.getLogger(__name__)

# One retry covers a Telegram blip; a real outage keeps failing and stays loud.
_RETRY_DELAY_SECONDS = 2.0


async def _deliver_once(
    bot: Bot, superadmin_id: int, photo, caption: str, reply_markup
) -> bool:
    try:
        await bot.send_photo(
            superadmin_id, photo=photo, caption=caption, reply_markup=reply_markup
        )
        return True
    except Exception as exc:
        logger.error(
            "failed to notify superadmin %s of a receipt: %s", superadmin_id, exc
        )
        return False


async def send_receipt_to_superadmins(
    bot: Bot,
    *,
    photo,
    caption: str,
    reply_markup,
    request_id: int,
    kind: str,
) -> int:
    """Send one receipt to every superadmin; return how many received it.

    Never raises: the request is already durable in the review queue, and a
    delivery problem must not undo the customer's submission.
    """
    superadmins = settings.superadmin_id_list
    if not superadmins:
        logger.error(
            "receipt #%s (%s) could not be announced: no superadmin is configured",
            request_id,
            kind,
        )
        return 0

    delivered = 0
    for superadmin_id in superadmins:
        if await _deliver_once(bot, superadmin_id, photo, caption, reply_markup):
            delivered += 1
            continue
        await asyncio.sleep(_RETRY_DELAY_SECONDS)
        if await _deliver_once(bot, superadmin_id, photo, caption, reply_markup):
            delivered += 1

    if not delivered:
        logger.critical(
            "receipt #%s (%s) reached no superadmin — it is waiting in the review queue",
            request_id,
            kind,
        )
    return delivered
