"""«ادمین ویژه»: sub-admins billed for the traffic their users really use.

A metered sub-admin never buys GB. MIT Panel stops limiting or charging their
user changes (see AdminLimiter), and once a week — the same Friday run as
everyone else — they get an ordinary invoice for the traffic used since the
last one. Ordinary invoice, ordinary rules: the same lock, the same receipt
flow, the same profit booking (its `usage_gb` is costed, it grants nothing).

The meter is Marzban's own per-admin `users_usage`: a lifetime counter that
deleting or resetting users never lowers, read for every admin in one
`/api/admins` request per panel. Only a sudo "reset admin usage" lowers it;
the drop is folded into `offset`, so the effective counter
(`offset + last_raw`) never goes down — nothing is billed twice or negative.

What the reseller already paid for is never billed again, and what they
take back to normal mode is paid for. Their paid position is their balance
(`admins.traffic`) plus the quota their live users still have left
(Σ max(data_limit − used, 0)), and both switches keep it exact:

* enabling turns the live users' remaining quota into `credit`. Usage is
  covered by that credit first, then by the balance, and only the rest is
  invoiced — so a config sold before the mode is not billed a second time as
  its user consumes it;
* disabling "buys back" the quota the live users still hold from what is
  left of the credit and the balance: a shortfall goes on the final invoice, a
  surplus returns to the balance. After that every live user is genuinely
  paid for, so the normal refund rules apply to them again.

Every write that moves money — the prepaid draw, the invoice, the
`billed_through` mark — happens in one BEGIN IMMEDIATE transaction on the
shared SQLite file (the bot tables and `admins` live in one file). Marzban is
never called while that lock is held: reads happen first, then the write.
"""

from __future__ import annotations

import asyncio
import logging
import math
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from html import escape

from backend.bot import db, texts
from backend.bot.consumption_ledger import transaction
from backend.bot.units import bytes_to_gb
from backend.services.marzban import APIService as MarzbanAPI

logger = logging.getLogger(__name__)

GB = 1024**3
WEEKLY_PREFIX = "m:"
FINAL_PREFIX = "m:final:"
# A week whose bill would be smaller than this is carried to the next one
# instead of sending a 40-toman invoice. The final invoice ignores it.
MIN_INVOICE_AMOUNT = 1_000
DUE_DAYS = 7
POLL_SECONDS = 300


class MeteringError(Exception):
    """Refused or deferred; nothing was changed. Shown to the superadmin."""


@dataclass
class Settlement:
    delta: int = 0          # usage since the last settlement, bytes
    covered: int = 0        # of which covered by credit + prepaid balance
    billable: int = 0       # bytes invoiced (usage, plus the buy-back on disable)
    shortfall: int = 0      # of billable: quota live users keep after disable
    carried: int = 0        # usage left for next time (below the minimum)
    invoice_id: int | None = None
    amount: int = 0
    due_at: str | None = None
    skipped: bool = False   # this stamp was already settled
    # where the money sits afterwards
    credit_after: int = 0
    traffic_after: int = 0


def plan(delta: int, credit: int, traffic: int, price: float, *,
         final_outstanding: int | None = None, final: bool = False) -> Settlement:
    """The pure arithmetic of one settlement, shared by settle() and the
    confirm-screen previews so what the superadmin is shown is what is billed.

    `final_outstanding` (disable only): the quota live users still have left,
    to be bought back from the remaining credit and balance.
    """
    delta, credit = max(int(delta), 0), max(int(credit), 0)
    traffic = int(traffic)
    from_credit = min(delta, credit)
    credit -= from_credit
    from_balance = min(delta - from_credit, max(traffic, 0))
    traffic -= from_balance
    usage_billable = delta - from_credit - from_balance

    shortfall = 0
    if final_outstanding is not None:
        available = credit + max(traffic, 0)
        need = max(int(final_outstanding), 0)
        if available >= need:
            traffic = min(traffic, 0) + (available - need)
        else:
            shortfall = need - available
            traffic = min(traffic, 0)
        credit = 0

    billable = usage_billable + shortfall
    amount = 0
    if billable:
        if not (math.isfinite(price) and price > 0):
            raise MeteringError("قیمت هر گیگ برای این ادمین تعیین نشده است")
        amount = round(bytes_to_gb(billable) * price)
    carried = 0
    if not final and usage_billable and amount < MIN_INVOICE_AMOUNT:
        carried, billable, amount = usage_billable, 0, 0
    return Settlement(
        delta=delta, covered=from_credit + from_balance, billable=billable, shortfall=shortfall,
        carried=carried, amount=amount, credit_after=credit, traffic_after=traffic,
    )


def outstanding(users: list[dict]) -> int:
    """Quota live users still have left: what a normal-mode reseller holds."""
    total = 0
    for u in users:
        try:
            limit = int(u.get("data_limit") or 0)
            used = int(u.get("used_traffic") or 0)
        except (TypeError, ValueError):
            continue
        if limit > 0:  # an unlimited user holds no countable quota
            total += max(limit - used, 0)
    return total


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(when: datetime) -> str:
    return when.astimezone(timezone.utc).isoformat()


def week_stamp(now: datetime) -> str:
    from backend.bot.weekly import TEHRAN, _week_stamp

    return WEEKLY_PREFIX + _week_stamp(now.astimezone(TEHRAN))


def _key(name: str | None) -> str:
    # Marzban matches admin names case-insensitively.
    return (name or "").strip().lower()


# ------------------------------------------------------------------ reading


def account(conn: sqlite3.Connection, admin_id: int) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM metered_accounts WHERE admin_id = ?", (admin_id,)).fetchone()


def is_metered(admin_id: int | None) -> bool:
    """Hot path (every user change): one primary-key lookup."""
    if not admin_id:
        return False
    try:
        with db._connect() as conn:
            row = conn.execute(
                "SELECT enabled FROM metered_accounts WHERE admin_id = ?", (admin_id,)
            ).fetchone()
    except sqlite3.OperationalError:
        return False  # table not created yet (init_db has not run)
    return bool(row and row["enabled"])


def is_metered_username(username: str | None) -> bool:
    """For flows that only know the panel name (buying GB)."""
    if not username:
        return False
    try:
        with db._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM metered_accounts WHERE enabled = 1 AND username = ?", (username,)
            ).fetchone()
    except sqlite3.OperationalError:
        return False
    return row is not None


def enabled_accounts() -> list[dict]:
    try:
        with db._connect() as conn:
            rows = conn.execute(
                "SELECT * FROM metered_accounts WHERE enabled = 1 ORDER BY admin_id"
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [dict(r) for r in rows]


def effective(acct) -> int:
    return int(acct["offset"]) + int(acct["last_raw"])


def usage(admin_id: int) -> dict | None:
    """What the reseller's dashboard shows. None when not metered."""
    with db._connect() as conn:
        acct = account(conn, admin_id)
        if acct is None or not acct["enabled"]:
            return None
        admin = conn.execute("SELECT traffic FROM admins WHERE id = ?", (admin_id,)).fetchone()
    eff = effective(acct)
    return {
        "since": acct["enabled_at"],
        "used_bytes": max(eff - int(acct["baseline"]), 0),
        "unsettled_bytes": max(eff - int(acct["billed_through"]), 0),
        "prepaid_bytes": int(acct["credit"]) + max(int((admin["traffic"] if admin else 0) or 0), 0),
        "read_at": acct["last_read_at"],
    }


def _panel(conn: sqlite3.Connection, name: str) -> sqlite3.Row | None:
    return conn.execute("SELECT * FROM panels WHERE name = ?", (name,)).fetchone()


def _api_for(panel) -> MarzbanAPI:
    return MarzbanAPI(url=panel["url"], username=panel["username"], password=panel["password"])


async def read_counters(panel) -> dict[str, int]:
    """Every admin's raw users_usage on one panel, keyed case-insensitively.
    Raises MeteringError on anything short of a complete answer."""
    try:
        raw = await _api_for(panel).get_admin_usages()
    except Exception as exc:
        raise MeteringError(f"خواندن مصرف از مرزبان ناموفق بود: {exc}") from exc
    return {_key(name): value for name, value in raw.items()}


def _counter_for(counters: dict[str, int], username: str) -> int:
    value = counters.get(_key(username))
    if value is None:
        raise MeteringError(f"ادمین {username} روی مرزبان پیدا نشد")
    return value


def _event(conn, admin_id: int, kind: str, now: datetime, *, bytes_: int = 0,
           invoice_id: int | None = None, note: str | None = None) -> None:
    conn.execute(
        "INSERT INTO metered_events (admin_id, kind, bytes, invoice_id, at, note) VALUES (?, ?, ?, ?, ?, ?)",
        (admin_id, kind, int(bytes_), invoice_id, _iso(now), note),
    )


def apply_reading(conn: sqlite3.Connection, admin_id: int, raw: int, now: datetime) -> bool:
    """Record a counter reading. Returns True when Marzban's counter went
    down (an admin usage reset): the drop is folded into the offset."""
    acct = account(conn, admin_id)
    if acct is None:
        raise MeteringError("حساب مصرفی پیدا نشد")
    last = int(acct["last_raw"])
    reset = raw < last
    if reset:
        conn.execute(
            'UPDATE metered_accounts SET "offset" = "offset" + ?, alert_reset_at = ? WHERE admin_id = ?',
            (last, _iso(now), admin_id),
        )
        _event(conn, admin_id, "reset", now, bytes_=last, note=f"raw {last} -> {raw}")
    conn.execute(
        "UPDATE metered_accounts SET last_raw = ?, last_read_at = ? WHERE admin_id = ?",
        (int(raw), _iso(now), admin_id),
    )
    return reset


# ------------------------------------------------------------------ settling


def _already_settled(conn, admin_id: int, stamp: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM metered_events WHERE admin_id = ? AND kind = 'settle' AND note = ?",
        (admin_id, stamp),
    ).fetchone() is not None


def settle(conn: sqlite3.Connection, admin_id: int, stamp: str, now: datetime,
           price: float, *, final: bool = False, final_outstanding: int | None = None) -> Settlement:
    """Bill the usage since the last settlement (and on disable, buy back the
    quota live users keep). Must run inside transaction(); either everything
    below lands or nothing does."""
    acct = account(conn, admin_id)
    if acct is None or not acct["enabled"]:
        raise MeteringError("این ادمین مصرفی نیست")
    if _already_settled(conn, admin_id, stamp):
        return Settlement(skipped=True)
    admin = conn.execute("SELECT * FROM admins WHERE id = ?", (admin_id,)).fetchone()
    if admin is None or (admin["username"], admin["panel"]) != (acct["username"], acct["panel"]):
        raise MeteringError("نام یا پنل این ادمین عوض شده است؛ تسویه انجام نشد")

    eff = effective(acct)
    result = plan(
        eff - int(acct["billed_through"]), int(acct["credit"]), int(admin["traffic"] or 0), price,
        final_outstanding=final_outstanding, final=final,
    )
    if result.billable:
        if not admin["telegram_id"]:
            raise MeteringError("آیدی تلگرام این ادمین ثبت نشده؛ فاکتور قابل ارسال نیست")
        due_at = _iso(now + timedelta(days=DUE_DAYS))
        description = texts.METERED_INVOICE_DESCRIPTION.format(
            username=acct["username"],
            period=texts.METERED_FINAL_PERIOD if final else stamp[len(WEEKLY_PREFIX):],
            used=bytes_to_gb(result.delta),
            covered=bytes_to_gb(result.covered),
            payable=bytes_to_gb(result.billable - result.shortfall),
        )
        if result.shortfall:
            description += texts.METERED_INVOICE_BUYBACK.format(gb=bytes_to_gb(result.shortfall))
        result.invoice_id = db.insert_invoice(
            conn, telegram_id=int(admin["telegram_id"]), amount=result.amount,
            description=description, due_at=due_at, admin_username=acct["username"],
            week_stamp=stamp, usage_gb=bytes_to_gb(result.billable),
        )
        result.due_at = due_at
    conn.execute("UPDATE admins SET traffic = ? WHERE id = ?", (result.traffic_after, admin_id))
    conn.execute(
        "UPDATE metered_accounts SET billed_through = ?, credit = ? WHERE admin_id = ?",
        (eff - result.carried, result.credit_after, admin_id),
    )
    _event(conn, admin_id, "settle", now, bytes_=result.delta, invoice_id=result.invoice_id, note=stamp)
    return result


# ------------------------------------------------------------------ enabling / disabling


def _admin_and_panel(conn, admin_id: int):
    admin = conn.execute("SELECT * FROM admins WHERE id = ?", (admin_id,)).fetchone()
    if admin is None:
        raise MeteringError("ادمین پیدا نشد")
    panel = _panel(conn, admin["panel"]) if admin["panel"] else None
    if panel is None or panel["panel_type"] != "marzban":
        raise MeteringError("ادمین ویژه فقط برای پنل مرزبان است")
    if not panel["is_active"]:
        raise MeteringError("پنل این ادمین غیرفعال است")
    return admin, panel


def _in_other_mode(conn, admin) -> bool:
    if db.get_weekly_mode(admin["username"]):
        return True
    try:
        return conn.execute(
            "SELECT 1 FROM consumption_accounts WHERE admin_id = ?", (admin["id"],)
        ).fetchone() is not None
    except sqlite3.OperationalError:
        return False


async def _owned_users(panel, username: str) -> list[dict]:
    """Every user the admin owns, read in full or not at all."""
    try:
        users = await _api_for(panel).get_all_users_paginated(owners=[username])
    except Exception as exc:
        raise MeteringError(f"خواندن کاربران از مرزبان ناموفق بود: {exc}") from exc
    return [
        u for u in users
        if isinstance(u, dict) and u.get("username")
        and _key((u.get("admin") or {}).get("username")) == _key(username)
    ]


def _check_can_enable(conn, admin_id: int):
    admin, panel = _admin_and_panel(conn, admin_id)
    if (acct := account(conn, admin_id)) is not None and acct["enabled"]:
        raise MeteringError("این ادمین همین الان ویژه است")
    if not admin["is_active"]:
        raise MeteringError("این ادمین غیرفعال است")
    if _in_other_mode(conn, admin):
        raise MeteringError("اول پرداخت با تأخیر/مصرفی قبلی این ادمین را خاموش کنید")
    return admin, panel


async def preview_enable(admin_id: int) -> dict:
    """What enabling would start from, from fresh Marzban reads."""
    with db._connect() as conn:
        admin, panel = _check_can_enable(conn, admin_id)
    raw = _counter_for(await read_counters(panel), admin["username"])
    credit = outstanding(await _owned_users(panel, admin["username"]))
    return {
        "username": admin["username"],
        "panel": panel["name"],
        "counter_bytes": raw,
        "credit_bytes": credit,
        "balance_bytes": max(int(admin["traffic"] or 0), 0),
    }


async def enable(admin_id: int, by: int | None, now: datetime | None = None) -> dict:
    now = now or _now()
    info = await preview_enable(admin_id)
    with transaction() as conn:
        admin, _ = _check_can_enable(conn, admin_id)
        raw = info["counter_bytes"]
        conn.execute(
            """INSERT INTO metered_accounts
                   (admin_id, username, panel, enabled, enabled_at, enabled_by, disabled_at,
                    baseline, "offset", last_raw, last_read_at, billed_through, credit, alert_reset_at)
               VALUES (?, ?, ?, 1, ?, ?, NULL, ?, 0, ?, ?, ?, ?, NULL)
               ON CONFLICT(admin_id) DO UPDATE SET
                   username = excluded.username, panel = excluded.panel, enabled = 1,
                   enabled_at = excluded.enabled_at, enabled_by = excluded.enabled_by,
                   disabled_at = NULL, baseline = excluded.baseline, "offset" = 0,
                   last_raw = excluded.last_raw, last_read_at = excluded.last_read_at,
                   billed_through = excluded.billed_through, credit = excluded.credit,
                   alert_reset_at = NULL""",
            (admin_id, admin["username"], admin["panel"], _iso(now), by, raw, raw, _iso(now), raw,
             info["credit_bytes"]),
        )
        _event(conn, admin_id, "enable", now, bytes_=raw, note=f"by {by}; credit {info['credit_bytes']}")
    logger.info("metered billing enabled for %s at counter %s, credit %s",
                info["username"], info["counter_bytes"], info["credit_bytes"])
    return info


async def _disable_reads(admin_id: int):
    with db._connect() as conn:
        acct = account(conn, admin_id)
        if acct is None or not acct["enabled"]:
            raise MeteringError("این ادمین ویژه نیست")
        admin, panel = _admin_and_panel(conn, admin_id)
    username = acct["username"]
    raw = _counter_for(await read_counters(panel), username)
    users = await _owned_users(panel, username)
    return acct, admin, raw, users


def _effective_after(acct, raw: int) -> int:
    last = int(acct["last_raw"])
    return int(acct["offset"]) + (last + raw if raw < last else raw)


async def preview_disable(admin_id: int) -> dict:
    """The final invoice disabling would send, from fresh Marzban reads."""
    acct, admin, raw, users = await _disable_reads(admin_id)
    price = db.get_effective_price(acct["username"])
    r = plan(
        _effective_after(acct, raw) - int(acct["billed_through"]), int(acct["credit"]),
        int(admin["traffic"] or 0), price, final_outstanding=outstanding(users), final=True,
    )
    return {"username": acct["username"], "delta": r.delta, "covered": r.covered,
            "billable": r.billable, "shortfall": r.shortfall, "amount": r.amount,
            "outstanding": outstanding(users), "balance_after": max(r.traffic_after, 0)}


async def disable(admin_id: int, now: datetime | None = None) -> Settlement:
    """Final invoice (usage + buy-back of the quota live users keep), the
    ledger brought in line with Marzban so the usage sync charges nothing
    twice, switch off. Any read failure refuses the whole thing."""
    now = now or _now()
    acct, _, raw, users = await _disable_reads(admin_id)
    username = acct["username"]
    price = db.get_effective_price(username)

    with transaction() as conn:
        acct = account(conn, admin_id)
        if acct is None or not acct["enabled"]:
            raise MeteringError("این ادمین ویژه نیست")
        apply_reading(conn, admin_id, raw, now)
        result = settle(conn, admin_id, FINAL_PREFIX + _iso(now), now, price,
                        final=True, final_outstanding=outstanding(users))
        stamp = now.replace(tzinfo=None).isoformat(sep=" ")
        for u in users:
            # Every live user is paid for from here on (the buy-back above), so
            # the ledger records each at its current limit, as an ordinary
            # one: the usage sync then charges nothing that was settled here.
            conn.execute(
                """INSERT INTO marzban_users (username, owner, data_limit, source, created_at)
                   VALUES (?, ?, ?, 'bot', ?)
                   ON CONFLICT(owner, username) DO UPDATE SET data_limit = excluded.data_limit""",
                (u["username"], username, int(u.get("data_limit") or 0), stamp),
            )
        conn.execute(
            "UPDATE metered_accounts SET enabled = 0, disabled_at = ?, credit = 0 WHERE admin_id = ?",
            (_iso(now), admin_id),
        )
        _event(conn, admin_id, "disable", now, bytes_=result.delta, invoice_id=result.invoice_id,
               note=f"{len(users)} users, outstanding {outstanding(users)}, shortfall {result.shortfall}")
    logger.info("metered billing disabled for %s (final invoice %s)", username, result.invoice_id)
    return result


# ------------------------------------------------------------------ the loop


async def poll(now: datetime) -> list[str]:
    """Read every metered admin's counter, one request per panel. Returns
    superadmin notes (counter resets, unreadable panels)."""
    accounts = enabled_accounts()
    notes: list[str] = []
    by_panel: dict[str, list[dict]] = {}
    for acct in accounts:
        by_panel.setdefault(acct["panel"], []).append(acct)
    for panel_name, accts in by_panel.items():
        with db._connect() as conn:
            panel = _panel(conn, panel_name)
        if panel is None:
            continue
        try:
            counters = await read_counters(panel)
        except MeteringError as exc:
            logger.warning("metering: %s unreadable: %s", panel_name, exc)
            continue
        with transaction() as conn:
            for acct in accts:
                raw = counters.get(_key(acct["username"]))
                if raw is None:
                    continue
                if apply_reading(conn, acct["admin_id"], raw, now):
                    notes.append(texts.METERED_COUNTER_RESET.format(username=escape(acct["username"])))
    return notes


async def settle_week(now: datetime) -> list[tuple[dict, Settlement | MeteringError | None]]:
    """Friday: settle every metered admin not yet settled for this week.
    Observers are skipped, like every other kind of billing."""
    stamp = week_stamp(now)
    observers = set(db.list_observer_admins())
    pending = []
    for acct in enabled_accounts():
        if acct["username"] in observers:
            continue
        with db._connect() as conn:
            if _already_settled(conn, acct["admin_id"], stamp):
                continue
        pending.append(acct)
    if not pending:
        return []
    await poll(now)  # settle on a fresh reading
    out = []
    for acct in pending:
        try:
            price = db.get_effective_price(acct["username"])
            with transaction() as conn:
                out.append((acct, settle(conn, acct["admin_id"], stamp, now, price)))
        except MeteringError as exc:
            # Retried every cycle until it works; reported once per week.
            with transaction() as conn:
                first = conn.execute(
                    "SELECT 1 FROM metered_events WHERE admin_id = ? AND kind = 'deferred' AND note = ?",
                    (acct["admin_id"], stamp),
                ).fetchone() is None
                if first:
                    _event(conn, acct["admin_id"], "deferred", now, note=stamp)
            out.append((acct, exc if first else None))
    return out


async def notify_invoice(bot, telegram_id: int, invoice_id: int) -> bool:
    from backend.bot import keyboards
    from backend.bot.invoices import describe_due

    invoice = db.get_invoice(invoice_id)
    if invoice is None:
        return False
    try:
        await bot.send_message(
            telegram_id,
            texts.INVOICE_FOR_CUSTOMER.format(
                id=invoice.id, amount=invoice.amount, description=invoice.description,
                due=describe_due(invoice.due_at),
            ),
            reply_markup=keyboards.pay_invoice_kb(invoice.id),
        )
        return True
    except Exception:
        return False


async def run_cycle(bot, now: datetime, superadmin_ids: list[int]) -> None:
    from backend.bot.weekly import RUN_HOUR, SETTLEMENT_WEEKDAY, TEHRAN

    if not enabled_accounts():
        return
    notes = await poll(now)
    local = now.astimezone(TEHRAN)
    if local.weekday() == SETTLEMENT_WEEKDAY and local.hour >= RUN_HOUR:
        for acct, outcome in await settle_week(now):
            name = escape(acct["username"])
            if outcome is None:
                continue  # still deferred, already reported this week
            if isinstance(outcome, MeteringError):
                notes.append(texts.METERED_SETTLE_DEFERRED.format(username=name, error=escape(str(outcome))))
                continue
            if outcome.invoice_id:
                with db._connect() as conn:
                    tg = conn.execute("SELECT telegram_id FROM admins WHERE id = ?", (acct["admin_id"],)).fetchone()
                delivered = bool(tg and tg["telegram_id"]) and await notify_invoice(
                    bot, int(tg["telegram_id"]), outcome.invoice_id
                )
                notes.append(texts.METERED_SETTLED_SUPERADMIN.format(
                    username=name, used=bytes_to_gb(outcome.delta), covered=bytes_to_gb(outcome.covered),
                    payable=bytes_to_gb(outcome.billable), amount=outcome.amount, id=outcome.invoice_id,
                    note="" if delivered else texts.METERED_NOT_DELIVERED,
                ))
            else:
                notes.append(texts.METERED_SETTLED_NO_INVOICE.format(
                    username=name, used=bytes_to_gb(outcome.delta), covered=bytes_to_gb(outcome.covered),
                ))
    if notes:
        for chat_id in superadmin_ids:
            try:
                await bot.send_message(chat_id, "\n\n".join(notes))
            except Exception:
                logger.warning("could not send the metering report")


async def run_scheduler(bot) -> None:
    from backend.bot.config import bot_config

    await asyncio.sleep(30)
    while True:
        try:
            await run_cycle(bot, _now(), bot_config.superadmin_id_list)
        except Exception:
            logger.exception("metering cycle failed")
        await asyncio.sleep(POLL_SECONDS)
