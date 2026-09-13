"""Hands-off receipt approval, for when the superadmin is away.

While it is on, every receipt that arrives is approved a minute after it lands.
That minute is the superadmin's window: the receipt still reaches them with its
buttons, and starting a rejection inside it wins. Receipts already waiting when
it was switched on are left for a person — switching it on decides what happens
next, it doesn't wave the backlog through.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone
from html import escape

from aiogram import Bot

from backend.bot import texts
from backend.bot.approvals import AUTOMATIC, approve_request
from backend.bot import db
from backend.bot.config import bot_config as settings

logger = logging.getLogger(__name__)

DELAY = timedelta(minutes=1)
SWEEP_SECONDS = 10

# Receipts a superadmin has started rejecting. If they abandon the rejection the
# receipt just stays here, waiting for a person — the safe way round.
_held: set[int] = set()
# Approvals that failed once. Retrying every sweep would repeat the failure
# notice forever, so after one attempt a person takes over.
_failed: set[int] = set()


def is_enabled() -> bool:
    return db.get_setting("auto_approve_enabled") == "1"


def set_enabled(on: bool) -> None:
    if on:
        db.set_setting("auto_approve_since", datetime.now(timezone.utc).isoformat())
    db.set_setting("auto_approve_enabled", "1" if on else "0")


def hold(request_id: int) -> None:
    _held.add(request_id)


def release(request_id: int) -> None:
    _held.discard(request_id)


def caption_note() -> str:
    """Appended to a receipt's caption, so the superadmin knows the clock is running."""
    return texts.AUTO_APPROVE_CAPTION_NOTE if is_enabled() else ""


def _parse(stamp: str | None) -> datetime | None:
    try:
        return datetime.fromisoformat(stamp)
    except Exception:
        return None


async def _notify(bot: Bot, text: str) -> None:
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, text)
        except Exception:
            continue


async def sweep(bot: Bot) -> int:
    if not is_enabled():
        return 0
    since = _parse(db.get_setting("auto_approve_since"))
    if since is None:
        return 0

    now = datetime.now(timezone.utc)
    approved = 0
    for req in db.list_pending_requests():
        if req.id in _held or req.id in _failed:
            continue
        created = _parse(req.created_at)
        if created is None or created < since or now - created < DELAY:
            continue

        outcome = await approve_request(bot, req.id, AUTOMATIC)
        if outcome.ok:
            approved += 1
            await _notify(
                bot,
                texts.AUTO_APPROVED_NOTICE.format(
                    id=req.id,
                    kind=texts.KIND_LABELS.get(req.kind, req.kind),
                    telegram_id=req.admin_telegram_id,
                    amount=req.toman_amount,
                ),
            )
            continue

        current = db.get_request(req.id)
        still_pending = current is not None and current.status == "pending"
        if still_pending:
            _failed.add(req.id)
        # Someone approving it by hand in the meantime isn't a failure worth
        # reporting; anything that left money unaccounted for is.
        if still_pending or outcome.finished:
            await _notify(
                bot,
                texts.AUTO_APPROVE_FAILED_NOTICE.format(id=req.id, reason=escape(outcome.message)),
            )
    return approved


async def run_auto_approver(bot: Bot) -> None:
    while True:
        try:
            count = await sweep(bot)
            if count:
                logger.info(f"auto-approved receipts: {count}")
        except Exception as exc:  # one bad receipt must not stop the loop
            logger.error(f"auto-approve sweep failed: {exc}")
        await asyncio.sleep(SWEEP_SECONDS)
