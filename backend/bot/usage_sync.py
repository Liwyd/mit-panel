"""Twice-daily reconciliation of Marzban against what MIT Panel has billed.

The bot only ever sees users it created itself. A reseller who creates a user
straight on the Marzban panel gets a working config that nobody paid for, and
`admins.traffic` — which is only reduced when a user is added through the bot
— has no idea. So at 03:00 and 15:00 Tehran time each panel's live users are
compared against the `marzban_users` ledger; whatever the ledger has never
seen is charged to that reseller (allowed to drive their traffic negative),
and an invoice is issued for the debt that created.

Nothing is stopped automatically. An admin whose traffic has gone negative is
already blocked from creating new users by AdminLimiter.check_traffic_limit,
so the superadmin decides when to suspend them, and is told about it.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import TYPE_CHECKING
from zoneinfo import ZoneInfo

from backend.bot import db, texts
from backend.bot.invoices import due_at_for
from backend.bot.units import bytes_to_gb
from backend.db import crud
from backend.db.engin import sessionLocal

if TYPE_CHECKING:
    from aiogram import Bot

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")
# Local hours (Tehran) at which the sweep runs.
SYNC_HOURS = (3, 15)
# After a failed sweep, hold off this long instead of hammering a panel that
# is down; the slot is retried once the wait is over.
RETRY_DELAY = timedelta(minutes=15)
STAMP_KEY = "usage_sync_stamp"
ENABLED_KEY = "usage_sync_enabled"
RETRY_KEY = "usage_sync_retry_after"
PAGE_SIZE = 500
# Pacing. The sweep is meant to be unnoticeable on the server: panels are read
# strictly one after another (never in parallel), with a pause between panels
# and between the pages of a single panel, so no instant of the run has more
# than one panel's worth of work in flight.
BETWEEN_PANELS = 1.0  # seconds
PAGE_DELAY = 0.25  # seconds between pages of one panel's user list

GB = 1024**3


@dataclass
class LiveUser:
    username: str
    data_limit: int


@dataclass
class Charge:
    username: str
    amount: int
    reason: str
    data_limit: int = 0


@dataclass
class SyncPlan:
    charges: list[Charge] = field(default_factory=list)
    # Ledger rows with no live counterpart: forget them, never refund them.
    pruned: list[str] = field(default_factory=list)
    # Live users to write into the ledger without charging anything.
    adopted: list[LiveUser] = field(default_factory=list)
    # Set when the run must leave this admin alone entirely.
    skip_reason: str | None = None


def plan_charge(live: dict[str, LiveUser], ledger: dict[str, int]) -> SyncPlan:
    """Work out what one reseller owes, from live users and their ledger.

    `ledger` maps username -> the data_limit last accounted for. Each case
    below must stay distinct: an empty ledger is a first run (charging it
    would bill every reseller for users they already had), no live users at
    all means a read that went wrong rather than a panel emptied overnight,
    and a raised limit is one user's top-up rather than a new user.
    """
    if ledger and not live:
        return SyncPlan(skip_reason="panel reported no users at all")

    plan = SyncPlan()

    if not ledger:
        # First sight: adopt everything so the next run has a baseline, and
        # charge nothing retroactively.
        return SyncPlan(
            adopted=[LiveUser(name, user.data_limit) for name, user in live.items()]
        )

    for name, user in live.items():
        known = ledger.get(name)
        if known is None:
            if user.data_limit > 0:
                plan.charges.append(
                    Charge(name, user.data_limit, "created outside the bot", user.data_limit)
                )
            else:
                # Unlimited user: there is nothing to price it at, so it is
                # recorded (and stops being reported) without being charged.
                plan.adopted.append(user)
        elif user.data_limit > known:
            plan.charges.append(
                Charge(
                    name,
                    user.data_limit - known,
                    "limit raised outside the bot",
                    user.data_limit,
                )
            )
        elif user.data_limit < known:
            # Lowered upstream. The reseller already paid for that quota, so
            # nothing is refunded; the stored limit just comes down.
            plan.adopted.append(user)

    plan.pruned = [name for name in ledger if name not in live]
    return plan


def group_by_owner(users: list[dict]) -> dict[str, list[dict]]:
    """Bucket a panel's users by the Marzban admin that owns them.

    Users with `admin: null` belong to the panel itself and are nobody's to
    charge, so they are dropped here rather than billed to someone by
    accident.
    """
    grouped: dict[str, list[dict]] = {}
    for user in users:
        owner = str(((user.get("admin") or {}).get("username")) or "")
        if not owner:
            continue
        grouped.setdefault(owner, []).append(user)
    return grouped


def to_live_map(users: list[dict]) -> dict[str, LiveUser]:
    live: dict[str, LiveUser] = {}
    for user in users:
        name = str(user.get("username") or "")
        if not name:
            continue
        live[name] = LiveUser(name, int(user.get("data_limit") or 0))
    return live


def invoice_amount(invoice_gb: int, price_per_gb: float) -> int:
    """Toman to ask for. Kept separate so the rounding rule is testable."""
    return round(bytes_to_gb(invoice_gb) * price_per_gb)


def new_debt(before: int, after: int) -> int:
    """GB that became negative in this run.

    Traffic that was already positive was bought and paid for, so only the
    part that dipped below zero is owed — a reseller with 50 GB left who is
    charged 100 GB owes 50.
    """
    return max(0, -after) - max(0, -before)


def _read_panel_users(panel) -> list[dict]:
    """Read one panel's users, keeping only the fields the diff needs.

    Runs in its own thread and its own event loop: the HTTP calls and the JSON
    parsing are synchronous, so doing them on the main loop would freeze the
    bot and the dashboard for as long as a panel takes to answer. Only the
    three fields the comparison uses are kept — a panel's full user records are
    large, and holding them all at once is the memory spike this sweep exists
    to avoid.
    """
    from backend.services.marzban.api import APIService

    api = APIService(url=panel.url, username=panel.username, password=panel.password)
    # Raises instead of returning a partial list: acting on one would prune
    # every ledger row the pagination never reached.
    raw_users = asyncio.run(
        api.get_all_users_paginated(page_size=PAGE_SIZE, page_delay=PAGE_DELAY)
    )

    slim: list[dict] = []
    for user in raw_users:
        name = str(user.get("username") or "")
        if not name:
            continue
        owner = str(((user.get("admin") or {}).get("username")) or "")
        slim.append(
            {
                "username": name,
                "data_limit": user.get("data_limit") or 0,
                "admin": {"username": owner} if owner else None,
            }
        )
    return slim


def _sweep() -> list[str]:
    """Reconcile every Marzban panel, one at a time. Returns the report lines.

    Deliberately synchronous and sequential: this runs inside a worker thread,
    so panels are never fetched concurrently and the server never sees more
    than a single panel being read at once.
    """
    report: list[str] = []
    with sessionLocal() as db:
        panels = [p for p in crud.get_all_panels(db) if p.panel_type == "marzban"]
        ledger_all = crud.get_marzban_users_grouped(db)

        for index, panel in enumerate(panels):
            try:
                report.extend(_sync_panel(db, panel, ledger_all))
            except Exception as exc:
                logger.error(f"Usage sync failed for panel {panel.name}: {exc}")
                report.append(f"❌ {panel.name}: خطا در همگام‌سازی ({exc})")
            if index + 1 < len(panels):
                time.sleep(BETWEEN_PANELS)
    return report


def _sync_panel(db, panel, ledger_all) -> list[str]:
    raw_users = _read_panel_users(panel)
    grouped = group_by_owner(raw_users)

    lines: list[str] = []
    for owner, owner_users in grouped.items():
        # The panel's own service account is not a reseller and is never billed.
        if owner == panel.username:
            continue
        admin = crud.get_admin_by_username(db, owner)
        if admin is None:
            continue

        live = to_live_map(owner_users)
        owner_ledger = {
            name: int(row.data_limit or 0)
            for name, row in (ledger_all.get(owner) or {}).items()
        }
        plan = plan_charge(live, owner_ledger)
        if plan.skip_reason:
            lines.append(f"⚠️ {panel.name}/{owner}: {plan.skip_reason}")
            continue

        # Ledger first, traffic second. The two helpers commit on their own,
        # so this order is what makes a failure between them cost a charge
        # once rather than bill the same user twice on the next sweep.
        before = int(admin.traffic or 0)
        for user in plan.adopted:
            crud.record_marzban_user(
                db,
                username=user.username,
                owner=owner,
                data_limit=user.data_limit,
                source="baseline" if not owner_ledger else "sync",
            )
        for charge in plan.charges:
            crud.record_marzban_user(
                db,
                username=charge.username,
                owner=owner,
                data_limit=charge.data_limit,
                source="external",
            )
        for name in plan.pruned:
            crud.delete_marzban_user(db, owner=owner, username=name)

        for charge in plan.charges:
            crud.reduce_admin_traffic_debt(db, admin, charge.amount)
        after = int(admin.traffic or 0)

        if not plan.charges:
            continue

        charged_bytes = sum(c.amount for c in plan.charges)
        debt_bytes = new_debt(before, after)
        lines.append(
            f"🔸 {panel.name}/{owner}: {len(plan.charges)} کاربر خارج از ربات "
            f"({bytes_to_gb(charged_bytes):.1f} گیگ)"
        )
        if admin.telegram_id and debt_bytes > 0:
            invoice_id = _issue_invoice(db, admin, charged_bytes, debt_bytes)
            if invoice_id:
                lines.append(f"🧾 فاکتور #{invoice_id} صادر شد")
        if after < 0:
            lines.append(
                f"🛑 {panel.name}/{owner}: موجودی منفی "
                f"{bytes_to_gb(-after):.1f} گیگ — ربات فروش متوقف نشده است"
            )
    return lines


def _issue_invoice(db, admin, charged_bytes: int, debt_bytes: int) -> int | None:
    """Bill a reseller for the debt the sweep just created.

    The invoice is what the existing receipt flow pays: whoever uploads a
    receipt for it is approving a request tied to this invoice, and that
    approval is what credits the GB back.
    """
    price = db.get_effective_price(admin.username)
    amount = invoice_amount(debt_bytes, price)
    if amount <= 0:
        return None

    return db.create_invoice(
        telegram_id=admin.telegram_id,
        amount=amount,
        description=texts.USAGE_SYNC_INVOICE.format(
            extra_gb=f"{bytes_to_gb(charged_bytes):.1f}",
            debt_gb=f"{bytes_to_gb(debt_bytes):.1f}",
        ),
        due_at=due_at_for("today"),
        admin_username=admin.username,
        traffic_gb=bytes_to_gb(debt_bytes),
    )


def _slot_stamp(now: datetime) -> str:
    return f"{now.date()}@{now.hour}"


def should_run(now: datetime, stamp: str | None, retry_after: str | None) -> bool:
    """Whether this moment is an unattempted sweep that is not in a backoff."""
    if now.hour not in SYNC_HOURS:
        return False
    if stamp == _slot_stamp(now):
        return False
    if retry_after:
        try:
            if now < datetime.fromisoformat(retry_after):
                return False
        except ValueError:
            pass
    return True


async def run_usage_sync(bot: Bot) -> None:
    """Background task: wakes once a minute, sweeps on the hour slots."""
    logger.info("Usage sync scheduler started (%s Tehran)", SYNC_HOURS)
    while True:
        await asyncio.sleep(60)
        if db.get_setting(ENABLED_KEY) == "0":
            continue
        now = datetime.now(TEHRAN)
        if not should_run(now, db.get_setting(STAMP_KEY), db.get_setting(RETRY_KEY)):
            continue

        db.set_setting(STAMP_KEY, _slot_stamp(now))
        try:
            # Worker thread: the panel reads, JSON parsing and every database
            # write happen off the main loop, which keeps answering Telegram
            # and the dashboard throughout the sweep.
            report = await asyncio.to_thread(_sweep)
        except Exception as exc:
            logger.error(f"Usage sync aborted: {exc}")
            # Let this slot try again shortly instead of waiting a full day.
            db.set_setting(STAMP_KEY, "")
            db.set_setting(
                RETRY_KEY, (now + RETRY_DELAY).isoformat()
            )
            continue
        db.set_setting(RETRY_KEY, "")

        await _report(bot, report)


async def _report(bot: Bot, lines: list[str]) -> None:
    if not lines:
        return
    text = texts.USAGE_SYNC_REPORT.format(body="\n".join(lines))
    for admin_id in db.superadmin_id_list:
        try:
            await bot.send_message(admin_id, text)
        except Exception as exc:
            logger.warning(f"Could not send usage sync report to {admin_id}: {exc}")
