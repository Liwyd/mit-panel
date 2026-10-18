"""Weekly credit billing, on Tehran local time.

Two fixed points in the Persian week, both at 08:00 Asia/Tehran:
  • Wednesday — two days before the week ends: remind each debtor what they owe.
  • Friday — the end of the week: take what the wallet covers, tell each debtor
    what (if anything) is still outstanding, and send the superadmin the roster.

For consumption-mode panels, Friday settlement also invoices the growth of the
panel's own created-volume figure since the previous settlement: for each
reseller that is the sum of data_limit over their live users, read live from
the Marzban panel — exactly the figure the panel holds, never an approximation
of it. The previous figure lives in `created_volume_baselines`, which doubles
as the per-owner settled-this-week marker so a crashed run resumes safely.

Each run is stamped with its ISO year-week so a restart, or the loop ticking
more than once inside the same hour, can't double-send.
"""

from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from aiogram import Bot

from backend.bot import keyboards, texts
from backend.bot.invoices import describe_due, is_due
from backend.bot import db
from backend.bot.billing import apply_wallet_to_debts
from backend.bot.config import bot_config as settings
from backend.bot.units import bytes_to_gb
from backend.bot.usage_sync import _read_panel_users, group_by_owner

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")

# Python weekday(): Monday=0 ... Wednesday=2, Friday=4.
REMINDER_WEEKDAY = 2
SETTLEMENT_WEEKDAY = 4
RUN_HOUR = 8

# A flaky panel must not cost the week's invoices: read attempts (with
# growing backoff) before the panel's owners are deferred to next week.
PANEL_READ_ATTEMPTS = 3
PANEL_READ_BACKOFF = 5.0


def _week_stamp(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-{week:02d}"


def _already_ran(key: str, stamp: str) -> bool:
    return db.get_setting(key) == stamp


def _week_start(now: datetime) -> datetime:
    """Saturday 00:00 Tehran of the week containing `now` (Saturday=5)."""
    days_since_sat = (now.weekday() - 5) % 7
    return (now - timedelta(days=days_since_sat)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )


def _get_admin_row(username: str):
    """The admins row for a panel username, or None for a stale config."""
    from backend.db.engin import sessionLocal
    from backend.db import crud

    with sessionLocal() as db_session:
        return crud.get_admin_by_username(db_session, username)


def _transition_created_bytes(owner: str, week_start: datetime, now: datetime) -> int:
    """Ledger-recorded creations inside this Persian week.

    Only used for an owner with no baseline — their panel's previous figure
    was never recorded, so the live delta is unknown and past weeks must not
    be billed retroactively. Everything the mirror saw created this week is
    exactly recoverable; from the next settlement the live baseline takes over.
    """
    from backend.db.engin import sessionLocal
    from backend.db.model import MarzbanUsers

    start_utc = week_start.astimezone(timezone.utc).replace(tzinfo=None)
    end_utc = now.astimezone(timezone.utc).replace(tzinfo=None)
    with sessionLocal() as db_session:
        rows = (
            db_session.query(MarzbanUsers)
            .filter(
                MarzbanUsers.owner == owner,
                MarzbanUsers.created_at >= start_utc,
                MarzbanUsers.created_at < end_utc,
            )
            .all()
        )
    return sum(int(row.data_limit or 0) for row in rows)


async def _read_panel_with_retry(panel) -> list[dict] | None:
    """One panel's users, or None when it could not be read reliably.

    An empty result is treated as a failed read rather than an emptied panel:
    acting on it would zero every owner's figure and silently swallow their
    week. Retries are paced so a panel that is down costs seconds, not a
    settlement.
    """
    for attempt in range(PANEL_READ_ATTEMPTS):
        try:
            users = await asyncio.to_thread(_read_panel_users, panel)
        except Exception as exc:
            logger.warning(
                "settlement panel read failed for %s (attempt %d/%d): %s",
                panel.name,
                attempt + 1,
                PANEL_READ_ATTEMPTS,
                exc,
            )
            users = None
        if users:
            return users
        if attempt + 1 < PANEL_READ_ATTEMPTS:
            await asyncio.sleep(PANEL_READ_BACKOFF * (attempt + 1))
    return None


async def _settle_owner(
    bot: Bot,
    *,
    owner: str,
    admin,
    live_total: int,
    week_start: datetime,
    now: datetime,
    stamp: str,
) -> list[str]:
    """Invoice one reseller for the growth of their live created-volume figure.

    The baseline row is the single source of truth for both "what did they
    have last time" and "did this week already settle them": it is written
    only after the invoice exists (or when nothing is owed), so a crash in
    between re-runs into the same delta and the unique invoice index absorbs
    the duplicate. When the amount cannot be priced or delivered the baseline
    is deliberately held back, letting the figure accumulate instead of
    quietly disappearing.
    """
    lines: list[str] = []
    baseline = db.get_created_volume_baseline(owner)
    if baseline and baseline["week_stamp"] == stamp:
        return lines

    if baseline is None:
        delta = _transition_created_bytes(owner, week_start, now)
    else:
        delta = max(0, live_total - int(baseline["total_bytes"]))

    if delta <= 0:
        db.set_created_volume_baseline(owner, stamp, live_total)
        return lines

    consumed_gb = bytes_to_gb(delta)
    price_per_gb = db.get_effective_price(owner)
    telegram_id = admin.telegram_id
    amount = round(consumed_gb * price_per_gb) if price_per_gb else 0
    if not telegram_id or amount <= 0:
        lines.append(
            texts.SETTLEMENT_OWNER_UNBILLED.format(username=owner, gb=consumed_gb)
        )
        return lines

    if not db.consumption_invoice_exists(owner, stamp):
        due_at = (now + timedelta(days=7)).isoformat()
        description = f"مصرف هفتگی پنل {owner} — {stamp} ({consumed_gb:.1f} GB)"
        try:
            db.create_invoice(
                telegram_id=telegram_id,
                amount=amount,
                description=description,
                due_at=due_at,
                admin_username=owner,
                week_stamp=stamp,
            )
        except sqlite3.IntegrityError:
            # Unique (admin_username, week_stamp): a concurrent run won the
            # race; its invoice is this owner's, so fall through to the baseline.
            pass
        else:
            try:
                await bot.send_message(
                    telegram_id,
                    texts.CONSUMPTION_INVOICE_HEADER.format(
                        username=owner,
                        consumed_gb=consumed_gb,
                        amount=amount,
                        due=describe_due(due_at),
                    ),
                )
            except Exception:
                pass
            lines.append(
                texts.CONSUMPTION_INVOICE_SUPERADMIN.format(
                    username=owner,
                    telegram_id=telegram_id,
                    consumed_gb=consumed_gb,
                    amount=amount,
                )
            )

    db.set_created_volume_baseline(owner, stamp, live_total)
    return lines


async def _settle_consumption(
    bot: Bot, now: datetime, stamp: str
) -> tuple[list[str], list[str]]:
    """Phase 1: consumption mode — invoice every owner's grown panel figure.

    Each Marzban panel is read live once (never per owner), owners are bucketed
    exactly the way the usage sync buckets them, and each consumption-mode owner
    is settled against their stored baseline. An owner whose panel could not be
    read is held untouched so the untouched figure catches up automatically on
    the next successful week.
    """
    from backend.db.engin import sessionLocal
    from backend.db import crud

    invoice_lines: list[str] = []
    warning_lines: list[str] = []
    consumption_owners = db.list_consumption_enabled()
    if not consumption_owners:
        return invoice_lines, warning_lines

    with sessionLocal() as db_session:
        panels = [p for p in crud.get_all_panels(db_session) if p.panel_type == "marzban"]

    # Sessions are deliberately not held across the panel reads below: a read
    # can take minutes with its retries, and a borrowed connection must not sit
    # idle in the pool for that long.
    totals: dict[str, int] = {}
    unreadable_panels: set[str] = set()
    for panel in panels:
        users = await _read_panel_with_retry(panel)
        if not users:
            unreadable_panels.add(panel.name)
            warning_lines.append(
                texts.SETTLEMENT_PANEL_UNREADABLE.format(panel=panel.name)
            )
            continue
        for owner, owner_users in group_by_owner(users).items():
            if owner == panel.username:
                continue
            totals[owner] = totals.get(owner, 0) + sum(
                int(u.get("data_limit") or 0) for u in owner_users
            )

    week_start = _week_start(now)
    # Read once for the whole sweep: observers are skipped everywhere below,
    # and the baseline is deliberately left alone for them, so un-marking one
    # later bills the entire frozen gap in a single catch-up invoice.
    observers = set(db.list_observer_admins())
    for owner in consumption_owners:
        admin = _get_admin_row(owner)
        if admin is None:
            continue  # stale weekly_payment row: no panel, nobody to bill
        if owner in observers:
            invoice_lines.append(
                texts.SETTLEMENT_OBSERVER_SKIPPED.format(username=owner)
            )
            continue  # no invoice, no baseline update — frozen by definition
        if admin.panel in unreadable_panels:
            continue  # deferred as a whole; the panel warning explains it
        invoice_lines += await _settle_owner(
            bot,
            owner=owner,
            admin=admin,
            live_total=totals.get(owner, 0),
            week_start=week_start,
            now=now,
            stamp=stamp,
        )
    return invoice_lines, warning_lines


async def send_reminders(bot: Bot) -> int:
    """Wednesday: nudge every debtor with a pay button."""
    sent = 0
    observers = set(db.list_observer_admins())
    for debt in db.list_outstanding_debts():
        if not debt["telegram_id"] or debt["username"] in observers:
            continue
        try:
            await bot.send_message(
                debt["telegram_id"],
                texts.WEEKLY_REMINDER.format(username=debt["username"], amount=debt["amount"]),
                reply_markup=keyboards.pay_debt_kb(debt["username"]),
            )
            sent += 1
        except Exception:
            continue
    return sent


async def send_overdue_reminders(bot: Bot) -> int:
    """Chase every debt that survived its settlement date, once a day.

    Only debts already stamped overdue are chased: someone who bought on
    Saturday has until Friday to pay and must not be nagged in between.
    """
    sent = 0
    now = datetime.now(TEHRAN)
    observers = set(db.list_observer_admins())
    for debt in db.list_outstanding_debts():
        if not debt["telegram_id"] or not debt.get("overdue_since"):
            continue
        if debt["username"] in observers:
            continue  # observers are never chased
        try:
            since = datetime.fromisoformat(debt["overdue_since"])
            days = max(1, (now - since.astimezone(TEHRAN)).days)
        except Exception:
            days = 1
        try:
            await bot.send_message(
                debt["telegram_id"],
                texts.OVERDUE_REMINDER.format(
                    username=debt["username"], amount=debt["amount"], days=days
                ),
                reply_markup=keyboards.pay_debt_kb(debt["username"]),
            )
            sent += 1
        except Exception:
            continue
    return sent


async def send_invoice_reminders(bot: Bot) -> int:
    """Chase manual invoices once their deadline has arrived, once a day.

    Invoices with no deadline are never chased automatically — an open-ended
    invoice is a record, not a demand.
    """
    sent = 0
    day_stamp = datetime.now(TEHRAN).strftime("%Y-%m-%d")
    observers = set(db.list_observer_admins())
    for invoice in db.list_pending_invoices():
        if invoice.admin_username and invoice.admin_username in observers:
            continue  # no stamp either, so un-marking them resumes the chase
        if not is_due(invoice.due_at) or invoice.last_reminded_date == day_stamp:
            continue
        try:
            await bot.send_message(
                invoice.telegram_id,
                texts.INVOICE_REMINDER.format(
                    id=invoice.id,
                    amount=invoice.amount,
                    description=invoice.description or "—",
                    due=describe_due(invoice.due_at),
                ),
                reply_markup=keyboards.pay_invoice_kb(invoice.id),
            )
            sent += 1
        except Exception:
            pass
        # Stamped either way, so a blocked chat isn't retried every tick.
        db.set_invoice_reminded(invoice.id, day_stamp)
    return sent


async def run_settlement(bot: Bot) -> None:
    """Friday: invoice consumption growth, draw down wallets for delayed debts,
    tell each debtor where they stand, then report."""
    now = datetime.now(TEHRAN)
    stamp = _week_stamp(now)

    # --- Phase 1: Consumption mode — invoice growth of the live panel figure ---
    consumption_report_lines, settlement_warning_lines = await _settle_consumption(
        bot, now, stamp
    )

    # --- Phase 2: Delayed mode — existing debt settlement (unchanged) ---
    # Observers are frozen as a whole: no wallet drawdown, no overdue stamp,
    # no debtor DM and no roster line until the superadmin un-marks them.
    observers = set(db.list_observer_admins())
    debts = [d for d in db.list_outstanding_debts() if d["username"] not in observers]
    if debts:
        # Wallet is per person, so settle once per owner rather than once per panel.
        paid_by_panel: dict[str, int] = {}
        for telegram_id in {d["telegram_id"] for d in debts if d["telegram_id"]}:
            for entry in apply_wallet_to_debts(telegram_id, skip_usernames=observers):
                paid_by_panel[entry["username"]] = entry["paid"]

        delayed_report_lines: list[str] = []
        for debt in debts:
            username = debt["username"]
            telegram_id = debt["telegram_id"]
            paid = paid_by_panel.get(username, 0)
            remaining = db.get_debt(username)
            if remaining > 0:
                # Survived its settlement date — from now on it gets chased daily.
                db.mark_overdue(username)

            if telegram_id:
                try:
                    if remaining <= 0:
                        await bot.send_message(
                            telegram_id,
                            texts.WEEKLY_WALLET_SETTLED.format(
                                username=username,
                                paid=paid,
                                balance=db.get_wallet_balance(telegram_id),
                            ),
                        )
                    else:
                        await bot.send_message(
                            telegram_id,
                            texts.WEEKLY_WALLET_PARTIAL.format(
                                username=username, paid=paid, remaining=remaining
                            ),
                            reply_markup=keyboards.pay_debt_kb(username),
                        )
                except Exception:
                    pass

            delayed_report_lines.append(
                texts.WEEKLY_SETTLEMENT_LINE.format(
                    username=username,
                    amount=remaining if remaining > 0 else paid,
                    note=texts.WEEKLY_SETTLEMENT_PAID_NOTE if remaining <= 0 else "",
                )
            )
    else:
        delayed_report_lines = []

    # --- Send combined report to superadmins ---
    report_parts = []
    if consumption_report_lines:
        report_parts.append("📊 فاکتورهای مصرف هفتگی:\n\n" + "".join(consumption_report_lines))
    if delayed_report_lines:
        report_parts.append(
            texts.WEEKLY_SETTLEMENT_LIST_HEADER + "".join(delayed_report_lines)
        )
    if settlement_warning_lines:
        report_parts.append(
            texts.SETTLEMENT_WARNINGS_HEADER + "".join(settlement_warning_lines)
        )
    if not report_parts:
        report_parts.append(texts.WEEKLY_SETTLEMENT_NONE)

    report = "\n\n".join(report_parts)
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, report)
        except Exception:
            continue


async def tick(bot: Bot) -> None:
    now = datetime.now(TEHRAN)
    if now.hour != RUN_HOUR:
        return
    stamp = _week_stamp(now)

    # Manual invoices are chased every day their deadline has passed, including
    # Wednesday and Friday — they're unrelated to the weekly panel billing cycle.
    invoice_count = await send_invoice_reminders(bot)
    if invoice_count:
        logger.info(f"invoice reminders sent: {invoice_count}")

    if now.weekday() == REMINDER_WEEKDAY and not _already_ran("weekly_reminder_week", stamp):
        count = await send_reminders(bot)
        db.set_setting("weekly_reminder_week", stamp)
        logger.info(f"weekly reminders sent: {count}")

    if now.weekday() == SETTLEMENT_WEEKDAY and not _already_ran("weekly_settlement_week", stamp):
        await run_settlement(bot)
        db.set_setting("weekly_settlement_week", stamp)
        logger.info("weekly settlement completed")

    # Every other day, chase whatever is still unpaid. Wednesday and Friday are
    # skipped because those days already send their own message.
    if now.weekday() not in (REMINDER_WEEKDAY, SETTLEMENT_WEEKDAY):
        day_stamp = now.strftime("%Y-%m-%d")
        if db.get_setting("overdue_reminder_date") != day_stamp:
            count = await send_overdue_reminders(bot)
            db.set_setting("overdue_reminder_date", day_stamp)
            if count:
                logger.info(f"overdue reminders sent: {count}")


async def run_weekly_scheduler(bot: Bot) -> None:
    while True:
        try:
            await tick(bot)
        except Exception as exc:  # a bad week must not kill the loop
            logger.error(f"weekly scheduler failed: {exc}")
        await asyncio.sleep(600)
