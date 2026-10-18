"""Lock a reseller out of both MIT Panel and Marzban while they owe money,
and hand both back the moment they don't.

A lock writes one known password (``LOCK_PASSWORD``) into Marzban first —
remote-first, because Marzban is what actually stops the reseller's sales bots
and user management — then into MIT Panel's local copies, and records the
admin's exact original password in the bot database so the restore is a
byte-for-byte return, not a guess. Nothing local is flipped until Marzban has
accepted the change; a failure mid-way compensates back toward the original.

The inverse is just as strict: the original password is pushed back to
Marzban first, and the lock row only disappears after that succeeds, so a
half-finished release leaves the lock in place to be retried rather than an
admin locked out with no way back in.

Both transitions are idempotent under process death: every step can be
re-run after a crash and converge on the correct end state.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot

from backend.bot import db
from backend.bot import texts
from backend.bot.config import bot_config
from backend.db import crud
from backend.db.engin import sessionLocal
from backend.services.marzban.api import APIService

logger = logging.getLogger(__name__)

# Written to both Marzban and MIT Panel while locked. Known by design: the
# superadmin can always unlock from the dashboard even if every notification
# was lost.
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

    A missing stamp never locks: an un-stamped debt has never been through a
    settlement, and an invoice without created_at shouldn't exist — either
    way, guessing would lock the wrong people.
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
    """Any reason at all to keep this admin locked — no grace, no filtering.

    Once locked, even a hair of remaining debt or one stale pending invoice
    keeps the lock: releasing on a technicality and re-locking minutes later
    would thrash Marzban and the admin's dashboard for no reason.
    """
    for debt in db.list_outstanding_debts():
        if debt["username"] == admin_username:
            return True
    for invoice in db.list_pending_invoices():
        owner = invoice.admin_username or _username_for_telegram_id(
            invoice.telegram_id
        )
        if owner == admin_username:
            return True
    return False


def _obligated() -> dict[str, str]:
    """Admins past the grace period on an invoice or debt: username -> reason."""
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
        if _age_reached(invoice.created_at):
            obligated[owner] = "unpaid_invoice"
    return obligated


async def _remote_set_password(
    panel_url: str, panel_username: str, panel_password: str,
    admin_username: str, new_password: str,
) -> bool:
    """Ask Marzban (as the panel's sudo account) to set an admin's password.

    False means "Marzban does not have the new password" — never treat a
    non-200 or a transport error as success, or MIT Panel would hold a
    password Marzban never accepted and every later restore would fail.
    """
    api = APIService(
        url=panel_url, username=panel_username, password=panel_password
    )
    try:
        status = await api.update_admin_password(admin_username, new_password)
    except Exception as exc:
        logger.error(
            "Marzban unreachable while setting password for %s: %s",
            admin_username, exc,
        )
        return False
    if status != 200:
        logger.warning(
            "Marzban rejected password change for %s (status %s)",
            admin_username, status,
        )
        return False
    return True


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
    """Lock one admin; False if anything prevented the lock.

    Order: Marzban first, then MIT Panel's copies, then the row holding the
    original password. Every failure after the remote change compensates back
    toward the original so the admin is never half-locked.
    """
    if db.is_observer_admin(admin_username):
        return False

    with sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
        if admin is None:
            return False
        # Idempotent: already locked and recorded, nothing to do.
        if db.get_admin_lock(admin_username):
            return False
        if not admin.marzban_password:
            logger.error(
                "cannot lock %s: no stored Marzban password to lock or restore",
                admin_username,
            )
            return False
        panel = crud.get_panel_by_name(session, admin.panel)
        if panel is None or panel.panel_type != "marzban":
            logger.warning(
                "cannot lock %s: no Marzban panel named %r",
                admin_username, admin.panel,
            )
            return False
        if admin.username == panel.username:
            logger.error(
                "refusing to lock %s: that is the panel's own sudo account",
                admin_username,
            )
            return False
        original = admin.marzban_password
        panel_creds = (panel.url, panel.username, panel.password)

    if original == LOCK_PASSWORD:
        # The "already locked" case with a row was returned above, so MIT Panel
        # holding the lock password with no recorded original means the restore
        # copy is gone. Loudly, because unlocking this admin now means
        # inventing a password.
        logger.error(
            "%s already has the lock password and no recorded original; "
            "leaving as-is — unlock manually from the dashboard",
            admin_username,
        )
        return False

    ok = await _remote_set_password(
        panel_creds[0], panel_creds[1], panel_creds[2],
        admin_username, LOCK_PASSWORD,
    )
    if not ok:
        return False

    try:
        with sessionLocal() as session:
            admin = crud.get_admin_by_username(session, admin_username)
            if admin is None:
                raise RuntimeError("admin vanished mid-lock")
            crud.update_marzban_password(session, admin, LOCK_PASSWORD)
        db.upsert_admin_lock(admin_username, original, reason)
    except Exception:
        logger.exception("local write failed while locking %s; reverting", admin_username)
        await _remote_set_password(
            panel_creds[0], panel_creds[1], panel_creds[2],
            admin_username, original,
        )
        try:
            with sessionLocal() as session:
                admin = crud.get_admin_by_username(session, admin_username)
                if admin and admin.marzban_password == LOCK_PASSWORD:
                    crud.update_marzban_password(session, admin, original)
            db.delete_admin_lock(admin_username)
        except Exception:
            logger.exception("compensation failed while unlocking %s", admin_username)
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
    """Restore the exact original password and clear the lock.

    Marzban first again: if the remote restore fails the lock row stays and
    the next tick simply tries the same restore — never the reverse order,
    which would leave MIT Panel believing a password Marzban no longer has.
    """
    row = db.get_admin_lock(admin_username)
    if row is None:
        return False
    original = row["original_marzban_password"]

    with sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
        panel = crud.get_panel_by_name(session, admin.panel) if admin else None

    if admin is None or panel is None or panel.panel_type != "marzban":
        # Nothing left to restore into; drop the row so the tick stops
        # retrying forever against a panel that can't answer.
        logger.warning(
            "dropping lock for %s: admin or panel no longer exists",
            admin_username,
        )
        db.delete_admin_lock(admin_username)
        return False

    ok = await _remote_set_password(
        panel.url, panel.username, panel.password,
        admin_username, original,
    )
    if not ok:
        logger.warning(
            "could not restore Marzban password for %s; lock kept for retry",
            admin_username,
        )
        return False

    with sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
        if admin is not None:
            crud.update_marzban_password(session, admin, original)
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


async def tick(bot: Bot) -> None:
    """One full reconcile: release the settled, lock the newly overdue."""
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
