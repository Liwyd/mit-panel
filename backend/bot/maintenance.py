"""Monthly hosting invoices for explicitly enrolled sales bots.

Only local SQLite transactions move billing state. Network I/O happens outside
those transactions; a durable outbox retries the same invoice after failure.
Telegram delivery is at-least-once (a crash after send can repeat a notification),
but the unique period key makes the monetary charge exactly-once.
"""

from __future__ import annotations

import asyncio
import calendar
import logging
import threading
from contextlib import closing
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_CEILING, ROUND_HALF_UP
from html import escape
from uuid import uuid4
from zoneinfo import ZoneInfo

import httpx

from backend.bot import db, keyboards, texts
from backend.bot.config import bot_config
from backend.utils.settings_store import get_settings, update_settings

logger = logging.getLogger(__name__)
TEHRAN = ZoneInfo("Asia/Tehran")
SOURCE = "PriceDB / TGJU"
RATE_URL = "https://api.priceto.day/v1/latest/irr/euro"
HEALTH_URL = "https://api.priceto.day/v1/health"
MAX_QUOTE_AGE = timedelta(hours=72)
BATCH_SIZE = 50
_init_lock = threading.Lock()
_initialized: set[str] = set()


def initialize() -> None:
    path = db.bot_config.sqlite_path
    with _init_lock:
        if path not in _initialized:
            db.init_db()
            _initialized.add(path)


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def stamp(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def parse(value: str) -> datetime:
    if not isinstance(value, str):
        raise ValueError("Timestamp must be a string")
    result = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if result.tzinfo is None:
        raise ValueError("Timezone is required")
    return result.astimezone(timezone.utc)


def price_value(value) -> Decimal:
    try:
        if len(str(value)) > 32:
            raise ValueError("price too long")
        result = Decimal(str(value))
    except (InvalidOperation, ValueError):
        raise ValueError(texts.MAINT_BAD_PRICE) from None
    if (
        not result.is_finite()
        or not Decimal("0.01") <= result <= Decimal("10000")
        or result.as_tuple().exponent < -2
    ):
        raise ValueError(texts.MAINT_BAD_PRICE)
    return result.quantize(Decimal("0.01"))


def set_price(value) -> str:
    price = str(price_value(value))
    update_settings({"bot_maintenance_eur": price})
    logger.info("maintenance monthly price changed to EUR %s", price)
    return price


def anniversary(anchor: datetime, months: int) -> datetime:
    local = anchor.astimezone(TEHRAN)
    year, month = divmod(local.year * 12 + local.month - 1 + months, 12)
    return local.replace(
        year=year,
        month=month + 1,
        day=min(local.day, calendar.monthrange(year, month + 1)[1]),
    ).astimezone(timezone.utc)


def current_period(anchor: datetime, now: datetime) -> tuple[datetime, datetime, int]:
    local_anchor, local_now = anchor.astimezone(TEHRAN), now.astimezone(TEHRAN)
    months = max(
        0,
        (local_now.year - local_anchor.year) * 12
        + local_now.month
        - local_anchor.month,
    )
    if anniversary(anchor, months) > now and months:
        months -= 1
    return anniversary(anchor, months), anniversary(anchor, months + 1), months


@dataclass(frozen=True)
class Quote:
    rate_irr: Decimal
    time: datetime


def validate_quote(body: dict, health: dict, now: datetime) -> Quote:
    try:
        if not isinstance(body, dict) or not isinstance(health, dict):
            raise ValueError("Invalid quote response")
        rate = Decimal(str(body["price"]))
        quoted = parse(body["time"])
        latest = parse(health["latestDataAt"])
        successful = parse(health["lastSuccessAt"])
        valid = (
            body.get("success") is True
            and health.get("success") is True
            and health.get("status") == "ok"
            and health.get("lastRunOk") is True
            and rate.is_finite()
            and 0 < rate <= Decimal("1000000000000")
            and all(
                timedelta(minutes=-5) <= now - moment <= MAX_QUOTE_AGE
                for moment in (quoted, latest, successful)
            )
        )
        if not valid:
            raise ValueError("unhealthy or stale quote")
        return Quote(rate, quoted)
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise ValueError("Invalid or stale EUR market quote") from None


async def fetch_quote(now: datetime) -> Quote:
    async with httpx.AsyncClient(
        timeout=httpx.Timeout(15, connect=8),
        headers={
            "User-Agent": "MIT-Panel/3.3 (+https://github.com/Liwyd/mit-panel)",
            "Accept": "application/json",
        },
    ) as client:
        rate, health = await asyncio.gather(
            client.get(RATE_URL), client.get(HEALTH_URL)
        )
    rate.raise_for_status()
    health.raise_for_status()
    return validate_quote(rate.json(), health.json(), now)


# The ORM and bot ledger use the same SQLite file in production. Reading the
# owner here, in the billing transaction, prevents stale browser/ORM snapshots
# from charging someone after the bot was reassigned.
_BOTS = """
    SELECT b.id, b.name, b.url, COALESCE(b.created_at, '') AS created_at, b.is_active,
           a.id AS admin_id, a.username AS admin_username,
           a.telegram_id, a.is_active AS admin_active,
           EXISTS (SELECT 1 FROM observer_admins o WHERE o.admin_username = a.username) AS observer
    FROM telegram_bots b LEFT JOIN admins a ON a.id = b.admin_id
"""


def _matches(subscription, bot) -> bool:
    return bool(
        bot
        and all(
            subscription[key] == bot[target]
            for key, target in (
                ("bot_created_at", "created_at"),
                ("admin_id", "admin_id"),
                ("admin_username", "admin_username"),
                ("telegram_id", "telegram_id"),
            )
        )
    )


def _eligible(bot) -> bool:
    return bool(
        bot
        and bot["is_active"]
        and bot["admin_active"]
        and bot["telegram_id"]
        and isinstance(bot["telegram_id"], int)
        and bot["telegram_id"] > 0
        and not bot["observer"]
    )


def _reconcile(conn) -> None:
    # Also handles deleted rows and reused numeric bot/admin ids.
    conn.execute("""
        UPDATE maintenance_subscriptions AS s SET enabled = 0
        WHERE enabled = 1 AND NOT EXISTS (
            SELECT 1 FROM telegram_bots b JOIN admins a ON a.id = b.admin_id
            WHERE b.id = s.bot_id AND COALESCE(b.created_at, '') = s.bot_created_at
              AND b.url = s.bot_url AND a.id = s.admin_id
              AND a.username = s.admin_username AND a.telegram_id = s.telegram_id
        )
    """)


def list_billing() -> dict:
    initialize()
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        _reconcile(conn)
        bots = conn.execute(_BOTS + " ORDER BY b.id").fetchall()
        states = {
            r["bot_id"]: dict(r)
            for r in conn.execute("SELECT * FROM maintenance_subscriptions")
        }
        # Indexed latest-period lookups in one query, without loading history or
        # issuing a separate database query for every bot in the dashboard.
        latest_by_bot = {
            row["bot_id"]: dict(row)
            for row in conn.execute("""
            SELECT p.bot_id, p.invoice_id, i.status, i.amount, i.due_at, p.notified_at, p.last_error
            FROM telegram_bots b JOIN maintenance_periods p ON p.invoice_id = (
                SELECT invoice_id FROM maintenance_periods WHERE bot_id = b.id
                ORDER BY invoice_id DESC LIMIT 1
            ) JOIN invoices i ON i.id = p.invoice_id
        """)
        }
        items = []
        for bot in bots:
            state = states.get(bot["id"])
            matched = state and _matches(state, bot)
            latest = latest_by_bot.get(bot["id"])
            items.append(
                {
                    "bot_id": bot["id"],
                    "bot_name": bot["name"],
                    "admin_username": bot["admin_username"],
                    "enabled": bool(matched and state["enabled"]),
                    "eligible": _eligible(bot),
                    "next_due_at": state["next_due_at"] if matched else None,
                    "latest_invoice": dict(latest) if latest else None,
                }
            )
    return {
        "eur_price": str(price_value(get_settings()["bot_maintenance_eur"])),
        "bots": items,
    }


def set_enabled(bot_id: int, enabled: bool, now: datetime | None = None) -> None:
    initialize()
    now = now or utcnow()
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        bot = conn.execute(_BOTS + " WHERE b.id = ?", (bot_id,)).fetchone()
        if not bot:
            raise ValueError(texts.MAINT_BOT_NOT_FOUND)
        state = conn.execute(
            "SELECT * FROM maintenance_subscriptions WHERE bot_id = ?", (bot_id,)
        ).fetchone()
        if not enabled:
            conn.execute(
                "UPDATE maintenance_subscriptions SET enabled = 0 WHERE bot_id = ?",
                (bot_id,),
            )
        elif not _eligible(bot):
            raise ValueError(texts.MAINT_INELIGIBLE)
        elif state and _matches(state, bot):
            conn.execute(
                "UPDATE maintenance_subscriptions SET enabled = 1, bot_url = ? WHERE bot_id = ?",
                (bot["url"], bot_id),
            )
        else:
            conn.execute(
                """
                INSERT INTO maintenance_subscriptions
                    (bot_id, bot_created_at, bot_url, admin_id, admin_username, telegram_id, enabled, anchor_at, next_due_at)
                VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(bot_id) DO UPDATE SET
                    bot_created_at = excluded.bot_created_at, bot_url = excluded.bot_url,
                    admin_id = excluded.admin_id, admin_username = excluded.admin_username,
                    telegram_id = excluded.telegram_id, enabled = 1,
                    anchor_at = excluded.anchor_at, next_due_at = excluded.next_due_at
            """,
                (
                    bot_id,
                    bot["created_at"],
                    bot["url"],
                    bot["admin_id"],
                    bot["admin_username"],
                    bot["telegram_id"],
                    stamp(now),
                    stamp(now),
                ),
            )
    logger.info("maintenance billing bot_id=%s enabled=%s", bot_id, enabled)


def due_ids(now: datetime) -> list[int]:
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        _reconcile(conn)
        return [
            r[0]
            for r in conn.execute(
                """
            SELECT s.bot_id FROM maintenance_subscriptions s
            JOIN telegram_bots b ON b.id = s.bot_id JOIN admins a ON a.id = b.admin_id
            WHERE s.enabled = 1 AND s.next_due_at <= ? AND b.is_active = 1 AND a.is_active = 1
              AND NOT EXISTS (SELECT 1 FROM observer_admins o WHERE o.admin_username = a.username)
            ORDER BY s.next_due_at, s.bot_id LIMIT ?
        """,
                (stamp(now), BATCH_SIZE),
            )
        ]


def _notice(conn, key: str, message: str, now: datetime) -> None:
    for chat_id in bot_config.superadmin_id_list:
        conn.execute(
            """
            INSERT OR IGNORE INTO maintenance_notices(notice_key, chat_id, message, next_attempt_at)
            VALUES (?, ?, ?, ?)
        """,
            (key, chat_id, message, stamp(now)),
        )


def issue(bot_id: int, quote: Quote, now: datetime) -> int | None:
    # Quote may have arrived after an admin disabled/reassigned the bot. Recheck
    # everything under the same writer lock that inserts the invoice.
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        bot = conn.execute(_BOTS + " WHERE b.id = ?", (bot_id,)).fetchone()
        state = conn.execute(
            "SELECT * FROM maintenance_subscriptions WHERE bot_id = ?", (bot_id,)
        ).fetchone()
        if (
            not state
            or not state["enabled"]
            or not _matches(state, bot)
            or not _eligible(bot)
            or parse(state["next_due_at"]) > now
        ):
            return None
        price = price_value(get_settings()["bot_maintenance_eur"])
        # Round the per-euro rate before multiplying by the monthly fee.
        # Keep both raw and applied rates for historical reconciliation.
        rate_toman = int(
            (quote.rate_irr / 10000).to_integral_value(rounding=ROUND_CEILING) * 1000
        )
        amount = int((price * rate_toman).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if amount <= 0:
            raise ValueError("Maintenance amount rounds to zero")
        anchor = parse(state["anchor_at"])
        start, end, index = current_period(anchor, now)
        _, _, due_index = current_period(anchor, parse(state["next_due_at"]))
        skipped = max(0, index - due_index)
        # Unique period stays consumed even if a bill is paid or cancelled.
        existing = conn.execute(
            "SELECT invoice_id FROM maintenance_periods WHERE bot_id = ? AND anchor_at = ? AND period_start = ?",
            (bot_id, state["anchor_at"], stamp(start)),
        ).fetchone()
        conn.execute(
            "UPDATE maintenance_subscriptions SET next_due_at = ? WHERE bot_id = ?",
            (stamp(end), bot_id),
        )
        if existing:
            return None
        description = texts.MAINT_DESCRIPTION.format(
            bot=bot["name"],
            start=start.astimezone(TEHRAN).strftime("%Y-%m-%d"),
            end=end.astimezone(TEHRAN).strftime("%Y-%m-%d"),
        )
        invoice_id = db.insert_invoice(
            conn,
            telegram_id=bot["telegram_id"],
            amount=amount,
            description=description,
            due_at=None,
            admin_username=bot["admin_username"],
        )
        conn.execute(
            """
            INSERT INTO maintenance_periods
                (invoice_id, bot_id, anchor_at, period_start, period_end, bot_name,
                 euro_price, rate_irr, rate_toman, quote_at, source, skipped_periods, next_attempt_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                invoice_id,
                bot_id,
                state["anchor_at"],
                stamp(start),
                stamp(end),
                bot["name"],
                str(price),
                str(quote.rate_irr),
                rate_toman,
                stamp(quote.time),
                SOURCE,
                skipped,
                stamp(now),
            ),
        )
        if skipped:
            _notice(
                conn,
                f"skipped:{invoice_id}",
                texts.MAINT_SKIPPED.format(bot=escape(bot["name"]), count=skipped),
                now,
            )
    logger.info(
        "maintenance invoice created id=%s bot_id=%s amount=%s",
        invoice_id,
        bot_id,
        amount,
    )
    return invoice_id


def rate_allowed(now: datetime) -> bool:
    with closing(db._connect()) as conn, conn:
        row = conn.execute(
            "SELECT next_attempt_at FROM maintenance_rate_retry WHERE id = 1"
        ).fetchone()
        return not row or parse(row[0]) <= now


def rate_result(now: datetime, ok: bool) -> None:
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if ok:
            conn.execute("DELETE FROM maintenance_rate_retry WHERE id = 1")
        else:
            row = conn.execute(
                "SELECT failures FROM maintenance_rate_retry WHERE id = 1"
            ).fetchone()
            failures = min(7, (row[0] if row else 0) + 1)
            conn.execute(
                """
                INSERT INTO maintenance_rate_retry VALUES (1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET failures = excluded.failures, next_attempt_at = excluded.next_attempt_at
            """,
                (
                    failures,
                    stamp(now + timedelta(seconds=min(3600, 60 * 2 ** (failures - 1)))),
                ),
            )
            _notice(
                conn,
                "rate:" + now.astimezone(TEHRAN).strftime("%Y-%m-%d"),
                texts.MAINT_RATE_UNAVAILABLE,
                now,
            )


def _claim(table: str, now: datetime) -> dict | None:
    # Only two internal constant table names are passed, never request input.
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if table == "maintenance_periods":
            row = conn.execute(
                """
                SELECT p.rowid AS delivery_id, p.*, i.telegram_id, i.amount, i.description
                FROM maintenance_periods p JOIN invoices i ON i.id = p.invoice_id
                WHERE p.notified_at IS NULL AND p.next_attempt_at <= ?
                  AND (p.claim_until IS NULL OR p.claim_until <= ?) AND i.status = 'pending'
                ORDER BY p.next_attempt_at LIMIT 1
            """,
                (stamp(now), stamp(now)),
            ).fetchone()
        else:
            row = conn.execute(
                """
                SELECT rowid AS delivery_id, * FROM maintenance_notices
                WHERE sent_at IS NULL AND next_attempt_at <= ? AND (claim_until IS NULL OR claim_until <= ?)
                ORDER BY next_attempt_at LIMIT 1
            """,
                (stamp(now), stamp(now)),
            ).fetchone()
        if row is None:
            return None
        token = uuid4().hex
        conn.execute(
            f"UPDATE {table} SET claim_token = ?, claim_until = ? WHERE rowid = ?",
            (token, stamp(now + timedelta(minutes=5)), row["delivery_id"]),
        )
        return dict(row) | {"token": token}


def _finish(table: str, item: dict, now: datetime, error: str | None) -> None:
    with closing(db._connect()) as conn, conn:
        conn.execute("BEGIN IMMEDIATE")
        if error:
            delay = min(3600, 60 * 2 ** min(item["attempts"], 6))
            extra = ", last_error = ?" if table == "maintenance_periods" else ""
            values = [stamp(now + timedelta(seconds=delay))]
            if extra:
                values.append(error)
            conn.execute(
                f"UPDATE {table} SET attempts = attempts + 1, next_attempt_at = ?, claim_token = NULL, claim_until = NULL{extra} WHERE rowid = ? AND claim_token = ?",
                (*values, item["delivery_id"], item["token"]),
            )
            if table == "maintenance_periods":
                _notice(
                    conn,
                    f"delivery:{item['invoice_id']}",
                    texts.MAINT_DELIVERY_FAILED.format(id=item["invoice_id"]),
                    now,
                )
        else:
            column = "notified_at" if table == "maintenance_periods" else "sent_at"
            extra = ", last_error = NULL" if table == "maintenance_periods" else ""
            changed = conn.execute(
                f"UPDATE {table} SET {column} = ?, claim_token = NULL, claim_until = NULL{extra} WHERE rowid = ? AND claim_token = ?",
                (stamp(now), item["delivery_id"], item["token"]),
            ).rowcount
            if table == "maintenance_periods" and changed:
                # Undelivered bills have no deadline and cannot lock anyone.
                conn.execute(
                    "UPDATE invoices SET due_at = ? WHERE id = ? AND status = 'pending' AND due_at IS NULL",
                    (stamp(now + timedelta(days=3)), item["invoice_id"]),
                )


async def deliver(bot, now: datetime | None = None) -> None:
    for table in ("maintenance_periods", "maintenance_notices"):
        for _ in range(BATCH_SIZE):
            moment = now or utcnow()
            item = await asyncio.to_thread(_claim, table, moment)
            if item is None:
                break
            error = None
            try:
                if table == "maintenance_periods":
                    await bot.send_message(
                        item["telegram_id"],
                        texts.MAINT_INVOICE.format(
                            id=item["invoice_id"],
                            description=escape(item["description"]),
                            amount=item["amount"],
                        ),
                        reply_markup=keyboards.pay_invoice_kb(item["invoice_id"]),
                        request_timeout=20,
                    )
                else:
                    await bot.send_message(
                        item["chat_id"], item["message"], request_timeout=20
                    )
            except asyncio.CancelledError:
                raise  # claim expires after restart
            except Exception as exc:
                error = type(exc).__name__  # no tokens/URLs/customer details
                logger.warning(
                    "maintenance delivery failed table=%s id=%s error=%s",
                    table,
                    item["delivery_id"],
                    error,
                )
            await asyncio.to_thread(_finish, table, item, now or utcnow(), error)


async def tick(bot, now: datetime | None = None) -> None:
    await asyncio.to_thread(initialize)
    moment = now or utcnow()
    ids = await asyncio.to_thread(due_ids, moment)
    if ids and await asyncio.to_thread(rate_allowed, moment):
        try:
            quote = await fetch_quote(moment)
        except (httpx.HTTPError, ValueError, TypeError):
            logger.warning("maintenance EUR quote unavailable; invoices deferred")
            await asyncio.to_thread(rate_result, moment, False)
        else:
            await asyncio.to_thread(rate_result, moment, True)
            for bot_id in ids:
                try:
                    await asyncio.to_thread(issue, bot_id, quote, now or utcnow())
                except Exception:
                    logger.exception("maintenance issuance failed bot_id=%s", bot_id)
    await deliver(bot, now)


async def run_scheduler(bot) -> None:
    while True:
        try:
            await tick(bot)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("maintenance scheduler tick failed")
        await asyncio.sleep(60)
