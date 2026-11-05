"""Marzban integration for the consumption-credit ledger."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import sqlite3
from collections import defaultdict
from collections.abc import Awaitable, Callable
from contextlib import closing
from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from functools import wraps
from html import escape
from threading import Lock
from weakref import WeakValueDictionary

from sqlalchemy import text

from backend.bot import consumption_ledger as ledger, db, texts
from backend.bot.invoices import describe_due, due_at_for
from backend.bot.units import bytes_to_gb, gb_to_bytes
from backend.services.marzban.api import APIService, MarzbanAPIError, REQUEST_TIMEOUT

logger = logging.getLogger(__name__)
_owner_locks: WeakValueDictionary[str, asyncio.Lock] = WeakValueDictionary()
legacy_sweep_lock = Lock()
_active_mutations: set[int] = set()
INTENT_TIMEOUT = timedelta(seconds=6 * REQUEST_TIMEOUT)


def _owner_lock(username: str) -> asyncio.Lock:
    return _owner_locks.setdefault(username, asyncio.Lock())


def serialize_user_change(handler):
    """Serialize dashboard mutations with the owner's first consumption grant."""
    @wraps(handler)
    async def locked(admin_username, *args, **kwargs):
        async with _owner_lock(admin_username):
            return await handler(admin_username, *args, **kwargs)

    return locked


def enrollment(session, admin_id: int, *, lock: bool = False):
    # The panel can run with the bot disabled and its tables never initialized.
    if not session.execute(text(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'consumption_accounts'"
    )).scalar():
        return None
    params = {"id": admin_id}
    query = text("SELECT * FROM consumption_accounts WHERE admin_id = :id")
    tracked = session.execute(query, params).mappings().first()
    if tracked and lock:
        session.execute(text(
            "UPDATE consumption_accounts SET revision = revision WHERE admin_id = :id"
        ), params)
        tracked = session.execute(query, params).mappings().first()
    return tracked


def remove_closed_account(session, admin_id: int) -> None:
    tracked = enrollment(session, admin_id, lock=True)
    if tracked is None:
        return
    params = {"id": admin_id}
    outstanding = session.execute(text(
        """SELECT 1 FROM consumption_allocations
             WHERE admin_id = :id AND state <> 'ordinary' AND (active_bytes > 0 OR billable_bytes > 0)
           UNION ALL SELECT 1 FROM consumption_returns r LEFT JOIN invoices i ON i.id = r.invoice_id
             WHERE r.admin_id = :id AND r.available_bytes > 0 AND COALESCE(i.status, '') <> 'cancelled'
           UNION ALL SELECT 1 FROM consumption_settlements s JOIN invoices i ON i.id = s.invoice_id
             WHERE s.admin_id = :id AND i.status = 'pending'
           UNION ALL SELECT 1 FROM consumption_mutations WHERE admin_id = :id
           LIMIT 1"""
    ), params).scalar()
    if tracked["available_bytes"] or tracked["unbilled_deficit_bytes"] or outstanding:
        raise ledger.BillingDeferred("The reseller still has consumption quota or invoices")
    for table in (
        "consumption_users", "consumption_allocations", "consumption_returns",
        "consumption_settlements", "consumption_accounts",
    ):
        session.execute(text(f"DELETE FROM {table} WHERE admin_id = :id"), params)


def _owner(user: dict) -> str | None:
    admin = user.get("admin")
    return admin.get("username") if isinstance(admin, dict) else None


def _state(user: dict) -> ledger.UserState:
    generation = user.get("created_at")
    limit, used = user.get("data_limit"), user.get("used_traffic")
    if (
        not isinstance(generation, str) or not generation
        or (limit is not None and (type(limit) is not int or limit < 0))
        or type(used) is not int or used < 0
        or "data_limit" not in user
    ):
        raise MarzbanAPIError("Missing or invalid billing data for user")
    lifetime = user.get("lifetime_used_traffic")
    earlier_usage = max(0, lifetime - used) if type(lifetime) is int else 0
    return ledger.UserState(generation, limit or 0, used, earlier_usage)


def _panel_api(panel) -> APIService:
    return APIService(panel["url"], panel["username"], panel["password"])


async def _read_users(api: APIService, owners: list[str]) -> dict[str, dict[str, ledger.UserState]]:
    raw = await api.get_all_users_paginated(page_size=500, page_delay=0.25, owners=owners)
    users: dict[str, dict[str, ledger.UserState]] = {owner: {} for owner in owners}
    for user in raw:
        owner = _owner(user)
        if owner in users:
            users[owner][user["username"]] = _state(user)
    return users


def _purchase_target(conn: sqlite3.Connection, telegram_id: int, username: str):
    row = conn.execute(
        """SELECT a.id, a.panel, p.url, p.username, p.password
           FROM admins a JOIN panels p ON a.panel = p.name
           JOIN weekly_payment w ON w.username = a.username
           WHERE a.username = ? AND a.telegram_id = ? AND a.is_active = 1
             AND p.panel_type = 'marzban' AND p.is_active = 1 AND p.username <> a.username
             AND w.enabled = 1 AND w.mode = 'consumption'
             AND NOT EXISTS (SELECT 1 FROM observer_admins o WHERE o.admin_username = a.username)""",
        (username, telegram_id),
    ).fetchone()
    if row is None:
        raise ledger.BillingDeferred("Consumption purchases are unavailable for this panel")
    return row


async def grant(telegram_id: int, username: str, gb: float) -> int:
    """Grant once per accepted bot callback, initializing the ledger on first use."""
    async with _owner_lock(username):
        with closing(db._connect()) as conn:
            target = _purchase_target(conn, telegram_id, username)
            tracked = ledger.account(conn, target["id"])
        baseline = None
        initializing = tracked is None
        if initializing and not legacy_sweep_lock.acquire(blocking=False):
            raise ledger.BillingDeferred("The panel is reconciling its balance. Try again shortly.")
        try:
            if initializing:
                baseline = (await asyncio.to_thread(
                    lambda: asyncio.run(_read_users(_panel_api(target), [username]))
                ))[username]
            with ledger.transaction() as conn:
                current = _purchase_target(conn, telegram_id, username)
                if tuple(current) != tuple(target):
                    raise ledger.BillingDeferred("The reseller or Marzban connection changed")
                if ledger.account(conn, target["id"]) is None:
                    if baseline is None:
                        raise ledger.BillingDeferred("The reseller baseline changed")
                    ledger.enroll(conn, target["id"], baseline)
                ledger.grant(conn, target["id"], gb_to_bytes(gb))
                return conn.execute(
                    "SELECT traffic FROM admins WHERE id = ?", (target["id"],)
                ).fetchone()[0]
        finally:
            if initializing:
                legacy_sweep_lock.release()


def _pending(conn: sqlite3.Connection, admin_id: int):
    return conn.execute(
        "SELECT * FROM consumption_mutations WHERE admin_id = ?", (admin_id,)
    ).fetchone()


def _clear_pending(conn: sqlite3.Connection, admin_id: int) -> None:
    conn.execute("DELETE FROM consumption_mutations WHERE admin_id = ?", (admin_id,))
    ledger.bump_revision(conn, admin_id)


def _observed_effect(pending, before: ledger.UserState | None, after: ledger.UserState | None) -> bool:
    operation = pending["operation"]
    if operation == "delete":
        return after is None or after.generation != before.generation
    if operation == "create":
        return after is not None and after.limit == pending["expected_limit"]
    if after is None or after.generation != before.generation:
        return False
    if operation == "update":
        return after.limit == pending["expected_limit"]
    return after.used < before.used or after.earlier_usage > before.earlier_usage


def _observe(
    conn, admin_id: int, username: str, state: ledger.UserState | None,
    *, reset=False, ordinary_returns=False,
):
    previous = ledger.user_state(conn, admin_id, username)
    if state is not None and not state.limit and (previous is None or previous.limit):
        raise ledger.BillingDeferred("An unlimited Marzban user requires review")
    ledger.observe(conn, admin_id, username, state, force_reset=reset, ordinary_returns=ordinary_returns)
    if previous == state or (previous and state and previous.limit == state.limit):
        return
    owner = ledger.account(conn, admin_id)["username"]
    if state is None:
        conn.execute("DELETE FROM marzban_users WHERE owner = ? AND username = ?", (owner, username))
    else:
        conn.execute(
            """INSERT INTO marzban_users (owner, username, data_limit, source, created_at)
               VALUES (?, ?, ?, 'consumption', ?)
               ON CONFLICT(owner, username) DO UPDATE SET data_limit = excluded.data_limit""",
            (owner, username, state.limit, state.generation),
        )


def _recover(conn, pending, state: ledger.UserState | None) -> bool:
    admin_id, username = pending["admin_id"], pending["username"]
    if admin_id in _active_mutations or (
        datetime.now(timezone.utc) < datetime.fromisoformat(pending["started_at"]) + INTENT_TIMEOUT
    ):
        raise ledger.BillingDeferred("A Marzban change is still being verified")
    before = ledger.UserState(**json.loads(pending["before_state"])) if pending["before_state"] else None
    applied = _observed_effect(pending, before, state)
    _observe(conn, admin_id, username, state, ordinary_returns=applied)
    _clear_pending(conn, admin_id)
    return applied


async def mutate(
    admin_id: int, owner: str, master: APIService, username: str, operation: str,
    request: Callable[[dict | None], Awaitable[int]], expected_limit: int | None = None,
) -> tuple[int, str]:
    """Persist the intent, apply the upstream change, then post its accounting."""
    def owned_state(raw: dict | None) -> ledger.UserState | None:
        return _state(raw) if raw and _owner(raw) == owner else None

    with closing(db._connect()) as conn:
        pending = _pending(conn, admin_id)
    if pending:
        raw = await master.get_billing_user(pending["username"])
        if raw and _owner(raw) != owner:
            raise ledger.BillingDeferred("The Marzban user belongs to a different reseller")
        with ledger.transaction() as conn:
            if _pending(conn, admin_id) != pending:
                raise ledger.BillingDeferred("A Marzban change was just reconciled. Refresh and retry.")
            applied = _recover(conn, pending, owned_state(raw))
        if applied and (username, operation, expected_limit) == (
            pending["username"], pending["operation"], pending["expected_limit"]
        ):
            return 200, "User change confirmed"

    raw = await master.get_billing_user(username)
    before = owned_state(raw)
    if operation == "create" and raw is not None:
        return 409, "This username already exists on the panel"
    if operation != "create" and before is None:
        return 404, "User not found"

    with ledger.transaction() as conn:
        if _pending(conn, admin_id):
            raise ledger.BillingDeferred("A Marzban change is still being verified")
        _observe(conn, admin_id, username, before)
        balance = ledger._admin(conn, admin_id)["traffic"]
        required = 0
        if operation == "create":
            required = expected_limit
        elif operation == "update":
            required = max(0, expected_limit - max(before.limit, before.used))
        elif operation == "reset":
            required = min(before.limit, before.used)
        if required and required > balance:
            return 403, "Insufficient traffic for this user change"
        conn.execute(
            """INSERT INTO consumption_mutations
               (admin_id, username, operation, before_state, expected_limit, started_at)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (admin_id, username, operation, json.dumps(asdict(before)) if before else None,
             expected_limit, datetime.now(timezone.utc).isoformat()),
        )
        ledger.bump_revision(conn, admin_id)

    _active_mutations.add(admin_id)
    try:
        status = await request(raw)
        if 400 <= status < 500 and status not in (408, 429):
            with ledger.transaction() as conn:
                _clear_pending(conn, admin_id)
            return 400, "Marzban rejected the user change"
        if status != 200:
            raise ledger.BillingDeferred("Could not confirm the Marzban change")

        raw = await master.get_billing_user(username)
        if raw and _owner(raw) != owner:
            raise ledger.BillingDeferred("The Marzban user belongs to a different reseller")
        after = owned_state(raw)
        with ledger.transaction() as conn:
            pending = _pending(conn, admin_id)
            if pending is None:
                raise ledger.BillingDeferred("The Marzban change was reconciled. Refresh the user.")
            reset = operation == "reset" and after is not None and before.generation == after.generation
            if not reset and not _observed_effect(pending, before, after):
                raise ledger.BillingDeferred("Could not verify the result of the Marzban change")
            _observe(conn, admin_id, username, after, reset=reset, ordinary_returns=True)
            _clear_pending(conn, admin_id)
        return 200, "User change confirmed"
    finally:
        _active_mutations.discard(admin_id)


def _snapshot(stamp: str | None, hourly: bool) -> list[sqlite3.Row]:
    with closing(db._connect()) as conn:
        return conn.execute(
            """SELECT c.*, p.url, p.username AS panel_username, p.password,
                      p.panel_type, p.is_active AS panel_active
               FROM consumption_accounts c LEFT JOIN panels p ON p.name = c.panel
               WHERE NOT EXISTS (
                   SELECT 1 FROM observer_admins o WHERE o.admin_username = c.username
               ) AND (? OR NOT EXISTS (
                   SELECT 1 FROM consumption_settlements s
                   WHERE s.admin_id = c.admin_id AND s.week_stamp = ?
               )) ORDER BY c.panel, c.username""",
            (hourly, stamp),
        ).fetchall()


async def _sync_panel(
    owners: list[sqlite3.Row], now: datetime, stamp: str | None, warn: bool,
) -> list[str]:
    panel = owners[0]
    if panel["panel_type"] != "marzban" or not panel["panel_active"]:
        return [
            texts.CONSUMPTION_SYNC_DEFERRED.format(username=escape(owner["username"]))
            for owner in owners
        ] if warn else []
    api = APIService(panel["url"], panel["panel_username"], panel["password"])
    users = await _read_users(api, [owner["username"] for owner in owners])
    notes = []
    for owner in owners:
        try:
            notes.extend(await _sync_owner(api, owner, users[owner["username"]], now, stamp, warn))
        except Exception:
            logger.exception("Consumption reconciliation deferred for %s", owner["username"])
            if warn:
                notes.append(texts.CONSUMPTION_SYNC_DEFERRED.format(username=escape(owner["username"])))
    return notes


async def _sync_owner(api, owner, found, now: datetime, stamp: str | None, warn: bool) -> list[str]:
    admin_id, username = owner["admin_id"], owner["username"]
    with closing(db._connect()) as conn:
        known = {
            row[0] for row in conn.execute(
                "SELECT username FROM consumption_users WHERE admin_id = ?", (admin_id,)
            )
        }
        pending = _pending(conn, admin_id)
        if pending:
            known.add(pending["username"])
    for missing in sorted(known - found.keys()):
        raw = await api.get_billing_user(missing)
        if raw is not None:
            if _owner(raw) != username:
                raise ledger.BillingDeferred("A Marzban user changed ownership")
            found[missing] = _state(raw)
        await asyncio.sleep(0.05)

    estimates = 0
    price = db.get_effective_price(username)
    result = None
    deferred = False
    with ledger.transaction() as conn:
        tracked = ledger.account(conn, admin_id)
        if tracked is None or tracked["revision"] != owner["revision"]:
            raise ledger.BillingDeferred("A newer quota change occurred during the read")
        ledger._admin(conn, admin_id)
        if pending:
            _recover(conn, pending, found.get(pending["username"]))
        for name in sorted(known | found.keys()):
            state = found.get(name)
            previous = ledger.user_state(conn, admin_id, name)
            if previous and (state is None or previous.generation != state.generation):
                estimates += 1
            _observe(conn, admin_id, name, state)
        ordinary_invoice = _issue_ordinary_deficit(conn, admin_id, price)
        if stamp:
            try:
                result = ledger.settle(conn, admin_id, stamp, now, price)
            except ledger.BillingDeferred:
                logger.info("Consumption invoice deferred for %s", username, exc_info=True)
                deferred = True

    notes = []
    if estimates:
        notes.append(texts.CONSUMPTION_ESTIMATED_RETURNS.format(username=escape(username), count=estimates))
    if result and result.invoice_id:
        notes.append(texts.CONSUMPTION_INVOICE_SUPERADMIN.format(
            username=escape(username), telegram_id=result.telegram_id,
            consumed_gb=bytes_to_gb(result.allocated - result.discount), amount=result.amount,
        ))
    if deferred and warn:
        notes.append(texts.CONSUMPTION_SYNC_DEFERRED.format(username=escape(username)))
    if ordinary_invoice:
        notes.append(texts.CONSUMPTION_ORDINARY_DEFICIT.format(username=escape(username), id=ordinary_invoice))
    return notes


def _issue_ordinary_deficit(conn, admin_id: int, price: float) -> int | None:
    """Retain the existing direct-use debt invoice for quota beyond both pools."""
    from backend.bot.usage_sync import invoice_amount

    tracked = ledger.account(conn, admin_id)
    pending = tracked["unbilled_deficit_bytes"]
    if not pending:
        return None
    admin = ledger._admin(conn, admin_id)
    debt = min(pending, max(0, tracked["available_bytes"] - int(admin["traffic"] or 0)))
    invoice_id = None
    if debt:
        amount = invoice_amount(debt, price) if math.isfinite(price) and price > 0 else 0
        if not admin["telegram_id"] or amount <= 0:
            return None
        invoice_id = db.insert_invoice(
            conn, telegram_id=admin["telegram_id"], amount=amount,
            admin_username=admin["username"], traffic_gb=bytes_to_gb(debt), due_at=due_at_for("today"),
            description=texts.USAGE_SYNC_INVOICE.format(
                extra_gb=f"{bytes_to_gb(pending):.1f}", debt_gb=f"{bytes_to_gb(debt):.1f}",
            ),
        )
    conn.execute(
        "UPDATE consumption_accounts SET unbilled_deficit_bytes = 0 WHERE admin_id = ?", (admin_id,)
    )
    return invoice_id


async def _notify_pending(bot) -> None:
    now = datetime.now(timezone.utc)
    with closing(db._connect()) as conn:
        invoices = conn.execute(
            """SELECT i.* FROM consumption_settlements s JOIN invoices i ON i.id = s.invoice_id
               WHERE s.notified_at IS NULL AND i.status = 'pending'
                 AND (s.notify_after IS NULL OR s.notify_after <= ?)
               ORDER BY i.id LIMIT 50""",
            (now.isoformat(),),
        ).fetchall()
    for invoice in invoices:
        try:
            await bot.send_message(
                invoice["telegram_id"],
                texts.CONSUMPTION_LEDGER_NOTICE.format(
                    description=escape(invoice["description"]), amount=invoice["amount"],
                    due=describe_due(invoice["due_at"]),
                ),
            )
        except Exception:
            logger.warning("Could not deliver consumption invoice %s", invoice["id"])
            with ledger.transaction() as conn:
                conn.execute(
                    "UPDATE consumption_settlements SET notify_after = ? WHERE invoice_id = ?",
                    ((now + timedelta(hours=1)).isoformat(), invoice["id"]),
                )
            continue
        with ledger.transaction() as conn:
            conn.execute(
                "UPDATE consumption_settlements SET notified_at = ? WHERE invoice_id = ?",
                (datetime.now(timezone.utc).isoformat(), invoice["id"]),
            )


async def run_cycle(bot, now: datetime, stamp: str | None, superadmin_ids: list[int]) -> None:
    hour = now.strftime("%Y-%m-%dT%H")
    hourly = db.get_setting("consumption_reconciled_hour") != hour
    panels = defaultdict(list)
    if hourly or stamp:
        for owner in _snapshot(stamp, hourly):
            panels[owner["panel"]].append(owner)
    notes = []
    for owners in panels.values():
        try:
            notes.extend(await asyncio.to_thread(
                lambda: asyncio.run(_sync_panel(owners, now, stamp, hourly))
            ))
        except Exception:
            logger.exception("Could not read consumption panel %s", owners[0]["panel"])
            if hourly:
                notes.extend(
                    texts.CONSUMPTION_SYNC_DEFERRED.format(username=escape(owner["username"]))
                    for owner in owners
                )
    if hourly:
        db.set_setting("consumption_reconciled_hour", hour)
    if notes:
        for chat_id in superadmin_ids:
            try:
                await bot.send_message(chat_id, "\n".join(notes))
            except Exception:
                logger.warning("Could not send consumption reconciliation report")
    await _notify_pending(bot)


async def run_scheduler(bot) -> None:
    from backend.bot.config import bot_config
    from backend.bot.weekly import RUN_HOUR, SETTLEMENT_WEEKDAY, TEHRAN, _week_stamp

    while True:
        try:
            now = datetime.now(TEHRAN)
            friday = now.weekday() == SETTLEMENT_WEEKDAY and now.hour >= RUN_HOUR
            await run_cycle(bot, now, _week_stamp(now) if friday else None, bot_config.superadmin_id_list)
        except Exception:
            logger.exception("Consumption billing cycle failed")
        await asyncio.sleep(600)
