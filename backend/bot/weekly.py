"""Weekly credit billing, on Tehran local time.

Two fixed points in the Persian week, both at 08:00 Asia/Tehran:
  • Wednesday — two days before the week ends: remind each debtor what they owe.
  • Friday — the end of the week: take what the wallet covers, tell each debtor
    what (if anything) is still outstanding, and send the superadmin the roster.

For consumption-mode panels, Friday settlement also generates invoices based on
actual weekly usage (configs created during the week).

Each run is stamped with its ISO year-week so a restart, or the loop ticking
more than once inside the same hour, can't double-send.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from aiogram import Bot

from backend.bot import keyboards, texts
from backend.bot.invoices import describe_due, is_due
from backend.bot import db
from backend.bot.billing import apply_wallet_to_debts
from backend.bot.config import bot_config as settings

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")

# Python weekday(): Monday=0 ... Wednesday=2, Friday=4.
REMINDER_WEEKDAY = 2
SETTLEMENT_WEEKDAY = 4
RUN_HOUR = 8


def _week_stamp(now: datetime) -> str:
    year, week, _ = now.isocalendar()
    return f"{year}-{week:02d}"


def _already_ran(key: str, stamp: str) -> bool:
    return db.get_setting(key) == stamp


def _calculate_weekly_consumption(username: str) -> int:
    """Calculate bytes consumed during the current week (Saturday→Friday).

    Uses traffic_history snapshots taken hourly by the warning scanner.
    Consumption = decrease in remaining traffic, adjusted for any grants.
    """
    now = datetime.now(TEHRAN)
    # Find Saturday of this week (Saturday=5 in Python weekday)
    days_since_sat = (now.weekday() - 5) % 7
    week_start = (now - timedelta(days=days_since_sat)).replace(
        hour=0, minute=0, second=0, microsecond=0
    )
    since_date = week_start.strftime("%Y-%m-%d")

    history = db.get_traffic_history(username, since_date)
    if len(history) < 1:
        return 0

    first, last = history[0], history[-1]
    # Same formula as forecast.py: (remaining_then - remaining_now) + (granted_now - granted_then)
    consumed = (first["traffic_bytes"] - last["traffic_bytes"]) + (
        last["initial_bytes"] - first["initial_bytes"]
    )
    return max(0, consumed)


def _get_admin_telegram_id(username: str) -> int | None:
    """Look up the Telegram ID for a panel username from the main DB."""
    from backend.db.engin import sessionLocal
    from backend.db import crud

    with sessionLocal() as db_session:
        admin = crud.get_admin_by_username(db_session, username)
        if admin:
            return admin.telegram_id
    return None


def _consumption_invoice_exists(telegram_id: int, username: str, week_stamp: str) -> bool:
    """Check if a consumption invoice already exists for this admin this week."""
    for inv in db.list_pending_invoices(telegram_id):
        if inv.description and week_stamp in inv.description and username in inv.description:
            return True
    return False


async def send_reminders(bot: Bot) -> int:
    """Wednesday: nudge every debtor with a pay button."""
    sent = 0
    for debt in db.list_outstanding_debts():
        if not debt["telegram_id"]:
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
    for debt in db.list_outstanding_debts():
        if not debt["telegram_id"] or not debt.get("overdue_since"):
            continue
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
    for invoice in db.list_pending_invoices():
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
    """Friday: generate consumption invoices, draw down wallets for delayed debts,
    tell each debtor where they stand, then report."""
    now = datetime.now(TEHRAN)
    stamp = _week_stamp(now)

    # --- Phase 1: Consumption mode — generate invoices for actual usage ---
    consumption_report_lines: list[str] = []
    for username in db.list_consumption_enabled():
        telegram_id = _get_admin_telegram_id(username)
        if not telegram_id:
            continue

        consumed_bytes = _calculate_weekly_consumption(username)
        if consumed_bytes <= 0:
            continue

        price_per_gb = db.get_effective_price(username)
        if not price_per_gb:
            continue

        from backend.bot.units import bytes_to_gb
        consumed_gb = bytes_to_gb(consumed_bytes)
        amount = round(consumed_gb * price_per_gb)
        if amount <= 0:
            continue

        # Idempotency: skip if invoice already exists this week
        if _consumption_invoice_exists(telegram_id, username, stamp):
            continue

        # Merge any existing delayed debt into the consumption invoice
        existing_debt = db.get_debt(username)
        if existing_debt > 0:
            amount += existing_debt
            db.clear_debt(username)

        # Invoice deadline: next Friday (7 days)
        due_at = (now + timedelta(days=7)).isoformat()
        description = f"مصرف هفتگی پنل {username} — {stamp} ({consumed_gb:.1f} GB)"
        db.create_invoice(
            telegram_id=telegram_id,
            amount=amount,
            description=description,
            due_at=due_at,
        )

        # Notify admin
        try:
            await bot.send_message(
                telegram_id,
                texts.CONSUMPTION_INVOICE_HEADER.format(
                    username=username,
                    consumed_gb=consumed_gb,
                    amount=amount,
                    due=describe_due(due_at),
                ),
            )
        except Exception:
            pass

        consumption_report_lines.append(
            texts.CONSUMPTION_INVOICE_SUPERADMIN.format(
                username=username,
                telegram_id=telegram_id,
                consumed_gb=consumed_gb,
                amount=amount,
            )
        )

    # --- Phase 2: Delayed mode — existing debt settlement (unchanged) ---
    debts = db.list_outstanding_debts()
    if debts:
        # Wallet is per person, so settle once per owner rather than once per panel.
        paid_by_panel: dict[str, int] = {}
        for telegram_id in {d["telegram_id"] for d in debts if d["telegram_id"]}:
            for entry in apply_wallet_to_debts(telegram_id):
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
