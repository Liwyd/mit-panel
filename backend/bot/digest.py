"""The day in one message, sent to the superadmins each night.

Everything here is already visible somewhere in the bot; the point is not having
to go and look. What is worth being told unprompted is what changed today and
what is waiting: money taken, receipts still unreviewed, debts past their date,
and panels about to run dry.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime
from html import escape
from zoneinfo import ZoneInfo

from aiogram import Bot

from backend.bot import bills, db, panel_client, sales, texts
from backend.bot.config import bot_config as settings
from backend.bot.units import bytes_to_gb

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")
LOW_TRAFFIC_GB = 50.0
MAX_LISTED_PANELS = 15
MAX_LISTED_SETTLEMENTS = 10


def _who(telegram_id: int | None) -> str:
    if telegram_id is None:
        return "—"
    record = db.get_user(telegram_id) or {}
    return escape(record.get("full_name") or str(telegram_id))


async def build(now: datetime | None = None) -> str:
    now = now or datetime.now(TEHRAN)
    text = texts.DIGEST_HEADER.format(day=sales.format_day(now.date()))

    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    ledger = db.list_sales_since(midnight.astimezone(UTC).isoformat())
    today = [s for s in ledger if s.method not in db.NOT_SALES]
    if today:
        text += texts.DIGEST_SALES.format(
            amount=sum(s.amount for s in today),
            gb=round(sum(s.gb for s in today), 2),
            count=len(today),
        )
    else:
        text += texts.DIGEST_NO_SALES

    # Money that came in against weekly credit — reported separately so it never
    # inflates the day's sales, but still seen without going to look for it.
    settled = [s for s in ledger if s.method == db.SETTLEMENT_METHOD]
    if settled:
        listed = "".join(
            texts.DIGEST_SETTLED_LINE.format(username=s.username or "—", amount=s.amount)
            for s in settled[:MAX_LISTED_SETTLEMENTS]
        )
        if len(settled) > MAX_LISTED_SETTLEMENTS:
            listed += texts.DIGEST_SETTLED_MORE.format(
                count=len(settled) - MAX_LISTED_SETTLEMENTS
            )
        text += texts.DIGEST_SETTLED.format(
            amount=sum(s.amount for s in settled), count=len(settled), payers=listed
        )

    charged = [s for s in ledger if s.method == db.WALLET_CHARGE_METHOD]
    if charged:
        listed = "".join(
            texts.DIGEST_WALLET_CHARGE_LINE.format(who=_who(s.telegram_id), amount=s.amount)
            for s in charged[:MAX_LISTED_SETTLEMENTS]
        )
        if len(charged) > MAX_LISTED_SETTLEMENTS:
            listed += texts.DIGEST_SETTLED_MORE.format(
                count=len(charged) - MAX_LISTED_SETTLEMENTS
            )
        text += texts.DIGEST_WALLET_CHARGED.format(
            amount=sum(s.amount for s in charged), count=len(charged), payers=listed
        )

    pending = db.list_pending_requests()
    if pending:
        text += texts.DIGEST_PENDING.format(
            count=len(pending), amount=sum(p.toman_amount for p in pending)
        )
    else:
        text += texts.DIGEST_NO_PENDING

    overdue = [b for b in bills.open_bills(now=now) if b.days_overdue(now) is not None]
    if overdue:
        text += texts.DIGEST_OVERDUE.format(
            count=len(overdue), amount=sum(b.amount for b in overdue)
        )
    else:
        text += texts.DIGEST_NO_OVERDUE

    # The only part that needs the panel; an outage costs this section, not the
    # whole message.
    try:
        admins = await panel_client.list_all_admins()
    except Exception as exc:
        logger.error(f"digest could not read the panels: {exc}")
        return text + texts.DIGEST_PANELS_UNAVAILABLE

    low = sorted(
        (
            (a["username"], bytes_to_gb(a.get("traffic")))
            for a in admins
            if a.get("is_active") and bytes_to_gb(a.get("traffic")) < LOW_TRAFFIC_GB
        ),
        key=lambda entry: entry[1],
    )
    if not low:
        return text + texts.DIGEST_NO_LOW_PANELS

    listed = "".join(
        texts.DIGEST_LOW_PANEL_LINE.format(username=username, remaining_gb=remaining)
        for username, remaining in low[:MAX_LISTED_PANELS]
    )
    text += texts.DIGEST_LOW_PANELS.format(threshold=LOW_TRAFFIC_GB, panels=listed)
    if len(low) > MAX_LISTED_PANELS:
        text += texts.DIGEST_MORE_PANELS.format(count=len(low) - MAX_LISTED_PANELS)
    return text


async def tick(bot: Bot) -> bool:
    now = datetime.now(TEHRAN)
    if now.hour != settings.digest_hour:
        return False
    # Stamped by day so a restart inside the hour doesn't send it twice.
    stamp = now.strftime("%Y-%m-%d")
    if db.get_setting("digest_date") == stamp:
        return False

    text = await build(now)
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, text)
        except Exception as exc:
            logger.error(f"failed sending the digest to {superadmin_id}: {exc}")
    db.set_setting("digest_date", stamp)
    return True


async def run_digest_scheduler(bot: Bot) -> None:
    while True:
        try:
            if await tick(bot):
                logger.info("daily digest sent")
        except Exception as exc:  # a bad day must not kill the loop
            logger.error(f"digest scheduler failed: {exc}")
        await asyncio.sleep(300)
