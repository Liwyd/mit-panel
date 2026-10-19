"""Lock a reseller out of MIT Panel's dashboard while they owe money.

A lock swaps only the local bcrypt hash behind the admin's MIT Panel login
for a hash of a known password (``LOCK_PASSWORD``) and keeps the exact
original hash in the bot database, so payment restores byte-for-byte what
the admin had. Marzban is deliberately never contacted: the reseller's
Marzban password — and everything that runs on it, from sales bots to the
user sync — stays exactly as it was, in the exact order Marzban already has.

The lock row is written before the hash is flipped, so a crash between the
two can only ever leave an admin who is guarded but whose password still
works — never one who can log in with the lock password and no record of
how to get out. Releases restore the hash first and drop the row second,
so a half-finished release leaves the lock in place to be retried.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from backend.auth.hash import hash_password, verify_password
from backend.bot import db
from backend.bot import texts
from backend.bot.config import bot_config
from backend.db import crud
from backend.db.engin import sessionLocal

logger = logging.getLogger(__name__)

# Written into MIT Panel's local login hash while locked. Known by design:
# the guard at login rejects it, and the superadmin can always unlock from
# the dashboard even if every notification was lost.
LOCK_PASSWORD = "mitlockedpass"

# How long an invoice or overdue stamp must exist before it locks anything.
# Instant locks would punish an admin for the seconds between Friday's
# settlement and their payment attempt.
LOCK_GRACE = timedelta(hours=12)

# The monitor's own period; payment approvals also release immediately, so
# this is the safety net, not the only path back in.
TICK_SECONDS = 300

_REASON_FA = {
    "unpaid_invoice": "فاکتور پرداخت‌نشده",
    "unpaid_debt": "بدهی هفتگی پرداخت‌نشده",
}


def _age_reached(stamp: str | None) -> bool:
    """Whether an ISO timestamp is at least LOCK_GRACE old.

    A missing stamp never locks: an invoice with no due date is open-ended
    by choice, and an un-stamped debt has never been through a settlement —
    either way, guessing would lock the wrong people.
    """
    if not stamp:
        return False
    try:
        when = datetime.fromisoformat(stamp)
    except ValueError:
        logger.error("unparseable timestamp in lock check: %r", stamp)
        return False
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) - when >= LOCK_GRACE


def _username_for_telegram_id(telegram_id: int) -> str | None:
    """The single admin behind a Telegram id, if there is exactly one."""
    with sessionLocal() as session:
        admins = crud.get_admins_by_telegram_id(session, telegram_id)
    return admins[0].username if len(admins) == 1 else None


def has_obligation(admin_username: str) -> bool:
    """Whether this admin currently meets the lock criteria.

    Same predicate that would lock them (past-due invoice or overdue debt,
    both past the grace) — not "any pending invoice", so an admin whose only
    remaining bills still have days to run is never held. Exemption is not
    considered here: it suppresses locking, never releases a lock.
    """
    return admin_username in _obligated()


def _obligated() -> dict[str, str]:
    """Admins past the grace period on an invoice or debt: username -> reason.

    An invoice only counts once its own due_at has passed (plus grace) —
    locking on invoice age alone would slam the dashboard shut seconds after
    a 12-hour-old invoice that isn't due for a week.
    """
    obligated: dict[str, str] = {}
    for debt in db.list_outstanding_debts():
        username = debt["username"]
        if not username:
            continue
        if _age_reached(debt.get("overdue_since")):
            obligated[username] = "unpaid_debt"
    for invoice in db.list_pending_invoices():
        owner = invoice.admin_username or _username_for_telegram_id(
            invoice.telegram_id
        )
        if not owner or owner in obligated:
            continue
        if _age_reached(invoice.due_at):
            obligated[owner] = "unpaid_invoice"
    return obligated


async def _notify_superadmins(bot: Bot, text: str) -> None:
    for admin_id in bot_config.superadmin_id_list:
        try:
            await bot.send_message(admin_id, text)
        except Exception:
            pass


async def _notify_admin(bot: Bot, admin_username: str, text: str) -> None:
    with sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
    if not admin or not admin.telegram_id:
        return
    try:
        await bot.send_message(admin.telegram_id, text)
    except Exception:
        pass


async def lock_admin(
    bot: Bot, admin_username: str, reason: str = "unpaid_invoice"
) -> bool:
    """Lock one admin's MIT Panel login; False if anything prevented it."""
    if db.is_observer_admin(admin_username):
        return False
    if db.get_admin_lock(admin_username):
        return False  # already locked — idempotent

    with sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
        if admin is None:
            return False
        if not admin.hashed_password:
            logger.error(
                "cannot lock %s: no stored login hash to lock or restore",
                admin_username,
            )
            return False
        original_hash = admin.hashed_password
        # The row-was-missing check above already ran, so MIT Panel holding the
        # lock password here means the restore copy is gone. Loudly, because
        # unlocking now means inventing a password. A hash passlib can't even
        # parse is not the lock password and restores fine as a raw string.
        try:
            already_locked = verify_password(LOCK_PASSWORD, admin.hashed_password)
        except Exception:
            already_locked = False
        if already_locked:
            logger.error(
                "%s already has the lock password and no recorded original; "
                "leaving as-is — unlock from the dashboard",
                admin_username,
            )
            return False

    # Row first, hash second: a crash in between leaves a guarded admin whose
    # password still works, never an admin who can log in with the lock
    # password and no record of how to get out.
    db.upsert_admin_lock(admin_username, original_hash, reason)
    try:
        with sessionLocal() as session:
            admin = crud.get_admin_by_username(session, admin_username)
            if admin is None:
                raise RuntimeError("admin vanished mid-lock")
            admin.hashed_password = hash_password(LOCK_PASSWORD)
            session.commit()
    except Exception:
        logger.exception("local write failed while locking %s", admin_username)
        db.delete_admin_lock(admin_username)
        return False

    logger.info("locked admin %s (reason: %s)", admin_username, reason)
    await _notify_superadmins(
        bot,
        texts.ACCESS_LOCKED_SUPERADMIN.format(
            username=admin_username, reason=_REASON_FA.get(reason, reason)
        ),
    )
    await _notify_admin(bot, admin_username, texts.ACCESS_LOCKED_ADMIN)
    return True


async def release_admin(bot: Bot, admin_username: str) -> bool:
    """Restore the exact original login hash and clear the lock.

    Hash first, row second: if the write fails the row stays and the next
    tick simply retries, rather than an unlocked-by-row admin whose password
    is still the lock one.
    """
    row = db.get_admin_lock(admin_username)
    if row is None:
        return False

    with sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
        if admin is None:
            logger.warning(
                "dropping lock for %s: admin no longer exists", admin_username
            )
            db.delete_admin_lock(admin_username)
            return False
        admin.hashed_password = row["original_hashed_password"]
        session.commit()
    db.delete_admin_lock(admin_username)

    logger.info("released admin %s", admin_username)
    await _notify_superadmins(
        bot, texts.ACCESS_UNLOCKED_SUPERADMIN.format(username=admin_username)
    )
    await _notify_admin(bot, admin_username, texts.ACCESS_UNLOCKED_ADMIN)
    return True


async def release_if_clear(bot: Bot, admin_username: str) -> bool:
    """Called straight after money lands: unlock now if nothing is still owed."""
    if db.get_admin_lock(admin_username) is None:
        return False
    if has_obligation(admin_username):
        return False
    return await release_admin(bot, admin_username)


async def force_release_if_locked(bot: Bot, admin_username: str) -> bool:
    """Unlock regardless of what is still owed (observer marking, manual fix)."""
    if db.get_admin_lock(admin_username) is None:
        return False
    return await release_admin(bot, admin_username)


async def manual_unlock(bot: Bot, admin_username: str) -> str:
    """Superadmin override: restore now and suppress re-locking until clean.

    Returns ``"unlocked"`` (restored + exempt), ``"no_lock"`` (nothing to
    restore), ``"failed"`` (the restore did not go through, so no exemption —
    an exemption on top of a live lock would just confuse things) or
    ``"unknown"`` (no such admin). The exemption is dropped by the next tick
    that finds the admin no longer meets the lock criteria, so the next
    genuinely overdue bill locks them again as usual.
    """
    with sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
    if admin is None:
        return "unknown"
    if db.get_admin_lock(admin_username) is None:
        return "no_lock"
    if not await release_admin(bot, admin_username):
        return "failed"
    db.set_lock_exempt(admin_username)
    logger.info("manually unlocked admin %s (re-lock suppressed until clean)", admin_username)
    return "unlocked"


async def tick(bot: Bot) -> None:
    """One full reconcile: release the settled, lock the newly overdue."""
    # A superadmin override outlives settlement of the bills it covered; the
    # moment nothing is lock-worthy anymore it means nothing, so drop it.
    for username in db.list_lock_exempt():
        try:
            if not has_obligation(username):
                db.clear_lock_exempt(username)
        except Exception:
            logger.exception("exemption cleanup failed for %s", username)

    for row in db.list_admin_locks():
        username = row["admin_username"]
        try:
            if db.is_observer_admin(username):
                await force_release_if_locked(bot, username)
            elif not has_obligation(username):
                await release_admin(bot, username)
        except Exception:
            logger.exception("release reconcile failed for %s", username)

    for username, reason in _obligated().items():
        try:
            if db.is_observer_admin(username):
                continue
            if db.is_lock_exempt(username):
                continue
            if db.get_admin_lock(username):
                continue
            await lock_admin(bot, username, reason)
        except Exception:
            logger.exception("lock reconcile failed for %s", username)


async def run_access_lock_monitor(bot: Bot) -> None:
    """The supervised loop's entry point: tick, wait, tick again."""
    while True:
        await tick(bot)
        await asyncio.sleep(TICK_SECONDS)
