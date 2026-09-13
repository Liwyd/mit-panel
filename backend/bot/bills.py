"""One view of everything a customer owes.

Two things put someone in debt — a manual invoice, and a panel's weekly credit —
but to the person paying and to the superadmin chasing, they are the same thing:
an amount, a deadline, and how late it is. This turns both into a Bill, so every
screen that lists debts totals, sorts and describes them the same way.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from html import escape
from zoneinfo import ZoneInfo

from backend.bot import texts
from backend.bot.weekly import RUN_HOUR, SETTLEMENT_WEEKDAY
from backend.bot import db

TEHRAN = ZoneInfo("Asia/Tehran")


def _parse(stamp: str | None) -> datetime | None:
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(stamp).astimezone(TEHRAN)
    except Exception:
        return None


def next_settlement(now: datetime) -> datetime:
    """The Friday run a weekly debt is due at while it isn't late yet."""
    ahead = (SETTLEMENT_WEEKDAY - now.weekday()) % 7
    at = (now + timedelta(days=ahead)).replace(hour=RUN_HOUR, minute=0, second=0, microsecond=0)
    return at if at > now else at + timedelta(days=7)


@dataclass
class Bill:
    kind: str  # "invoice" or "weekly"
    telegram_id: int | None
    amount: int
    due: datetime | None  # None: an open-ended invoice, which is never late
    created: datetime | None = None
    last_warned: datetime | None = None
    invoice_id: int | None = None
    username: str | None = None  # the panel, for weekly credit
    description: str | None = None

    @property
    def key(self) -> str:
        """Stable reference for callback data."""
        return f"i:{self.invoice_id}" if self.kind == "invoice" else f"w:{self.username}"

    def days_overdue(self, now: datetime | None = None) -> int | None:
        """Whole days past the deadline (0 means it passed today), or None if not late."""
        now = now or datetime.now(TEHRAN)
        if self.due is None or now < self.due:
            return None
        return (now - self.due).days


def urgency(bill: Bill) -> tuple[int, int]:
    overdue = bill.days_overdue()
    return (overdue if overdue is not None else -1, bill.amount)


@dataclass
class Customer:
    telegram_id: int | None
    bills: list[Bill] = field(default_factory=list)

    @property
    def total(self) -> int:
        return sum(b.amount for b in self.bills)

    @property
    def worst_overdue(self) -> int:
        return max((urgency(b)[0] for b in self.bills), default=-1)


def open_bills(telegram_id: int | None = None, now: datetime | None = None) -> list[Bill]:
    now = now or datetime.now(TEHRAN)
    bills: list[Bill] = []
    for inv in db.list_pending_invoices(telegram_id):
        bills.append(
            Bill(
                kind="invoice",
                telegram_id=inv.telegram_id,
                amount=inv.amount,
                due=_parse(inv.due_at),
                created=_parse(inv.created_at),
                last_warned=_parse(inv.last_warned_at),
                invoice_id=inv.id,
                description=inv.description,
            )
        )
    for debt in db.list_outstanding_debts():
        if telegram_id is not None and debt["telegram_id"] != telegram_id:
            continue
        bills.append(
            Bill(
                kind="weekly",
                telegram_id=debt["telegram_id"],
                amount=debt["amount"],
                # Not late until Friday's settlement leaves it unpaid; from then on
                # it is late from that settlement, which is what overdue_since holds.
                due=_parse(debt.get("overdue_since")) or next_settlement(now),
                last_warned=_parse(debt.get("last_warned_at")),
                username=debt["username"],
            )
        )
    return bills


def by_customer(bills: list[Bill]) -> list[Customer]:
    """Group per person, most urgent first — both the people and their bills."""
    groups: dict[int | None, Customer] = {}
    for bill in bills:
        groups.setdefault(bill.telegram_id, Customer(bill.telegram_id)).bills.append(bill)
    customers = list(groups.values())
    for customer in customers:
        customer.bills.sort(key=urgency, reverse=True)
    customers.sort(key=lambda c: (c.worst_overdue, c.total), reverse=True)
    return customers


def find(key: str) -> Bill | None:
    """An open bill by its callback key; None once it's paid or cancelled."""
    return next((b for b in open_bills() if b.key == key), None)


def mark_warned(bill: Bill) -> None:
    if bill.kind == "invoice":
        db.mark_invoice_warned(bill.invoice_id)
    else:
        db.mark_debt_warned(bill.username)


# ---- rendering ---------------------------------------------------------------

def describe_timing(bill: Bill, now: datetime | None = None) -> str:
    now = now or datetime.now(TEHRAN)
    if bill.due is None:
        return texts.TIMING_OPEN
    overdue = bill.days_overdue(now)
    if overdue is None:
        left = (bill.due - now).days
        return texts.TIMING_DUE_IN.format(days=left) if left >= 1 else texts.TIMING_DUE_TODAY
    return texts.TIMING_OVERDUE.format(days=overdue) if overdue >= 1 else texts.TIMING_OVERDUE_TODAY


def _ago(moment: datetime, now: datetime) -> str:
    days = (now.date() - moment.date()).days
    return texts.WHEN_TODAY if days <= 0 else texts.WHEN_DAYS_AGO.format(days=days)


def _identity(telegram_id: int | None) -> tuple[str, str, str]:
    if telegram_id is None:
        return "—", "—", "—"
    record = db.get_user(telegram_id) or {}
    name = escape(record.get("full_name") or "—")
    mention = f"@{escape(record['username'])}" if record.get("username") else "—"
    return name, mention, str(telegram_id)


def render_summary(customers: list[Customer], now: datetime | None = None) -> str:
    now = now or datetime.now(TEHRAN)
    everything = [b for c in customers for b in c.bills]
    late = [b for b in everything if b.days_overdue(now) is not None]
    return texts.BILLS_SUMMARY.format(
        total=sum(b.amount for b in everything),
        customers=len(customers),
        count=len(everything),
        overdue_count=len(late),
        overdue_total=sum(b.amount for b in late),
    )


def render_customer(customer: Customer, now: datetime | None = None) -> str:
    now = now or datetime.now(TEHRAN)
    name, mention, telegram_id = _identity(customer.telegram_id)
    text = texts.BILLS_CUSTOMER_HEADER.format(
        name=name, mention=mention, telegram_id=telegram_id, total=customer.total
    )
    for bill in customer.bills:
        timing = describe_timing(bill, now)
        if bill.kind == "invoice":
            text += texts.BILL_INVOICE_ITEM.format(
                id=bill.invoice_id,
                amount=bill.amount,
                description=escape(bill.description or "—"),
                timing=timing,
            )
        else:
            text += texts.BILL_WEEKLY_ITEM.format(
                username=escape(bill.username or "—"), amount=bill.amount, timing=timing
            )
        if bill.last_warned:
            text += texts.BILL_LAST_WARNED.format(when=_ago(bill.last_warned, now))
    return text


def render_for_customer(bill: Bill, now: datetime | None = None) -> str:
    timing = describe_timing(bill, now)
    if bill.kind == "invoice":
        return texts.MY_BILL_INVOICE.format(
            id=bill.invoice_id,
            amount=bill.amount,
            description=escape(bill.description or "—"),
            timing=timing,
        )
    return texts.MY_BILL_WEEKLY.format(
        username=escape(bill.username or "—"), amount=bill.amount, timing=timing
    )


def render_warning(bill: Bill, now: datetime | None = None) -> str:
    now = now or datetime.now(TEHRAN)
    overdue = bill.days_overdue(now)
    if overdue:
        days_line = texts.WARN_DAYS_OVERDUE.format(days=overdue)
    elif bill.created and (now - bill.created).days >= 1:
        days_line = texts.WARN_DAYS_SINCE_ISSUED.format(days=(now - bill.created).days)
    else:
        days_line = texts.WARN_UNPAID

    if bill.kind == "invoice":
        subject = texts.WARN_SUBJECT_INVOICE.format(
            id=bill.invoice_id, description=escape(bill.description or "—")
        )
    else:
        subject = texts.WARN_SUBJECT_WEEKLY.format(username=escape(bill.username or "—"))

    # Weekly credit always belongs to a panel; an invoice may be for someone with none.
    has_panel = bill.kind == "weekly" or (
        bill.telegram_id is not None and db.is_user_linked(bill.telegram_id)
    )
    return texts.NONPAYMENT_WARNING.format(
        subject=subject,
        amount=bill.amount,
        days_line=days_line,
        service=texts.WARN_SERVICE_PANEL if has_panel else texts.WARN_SERVICE_GENERIC,
    )
