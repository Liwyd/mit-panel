"""Black Friday: pricing, eligibility, debt settlement at the event rate, stats.

Pure business rules, kept apart from the handlers so they can be tested without
a bot. Nothing here talks to Telegram; the one thing it does touch is the
wallet/debt/ledger tables through `backend.bot.db`.

Everything money-shaped is decided at the moment it is quoted and then carried
with the request, so an approval that happens after the event ended still
honours the price the customer was shown.

`backend.bot.bills` is imported inside functions on purpose: it pulls in
`weekly`, which pulls in `keyboards`, and `keyboards` imports this module for
`is_active()`.
"""

from __future__ import annotations

import logging
import math
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from html import escape
from zoneinfo import ZoneInfo

from backend.bot import db, texts

logger = logging.getLogger(__name__)

TEHRAN = ZoneInfo("Asia/Tehran")

# Toman per GB during the event.
BF_PRICE_PER_GB = 2400
# (paid GB, gift GB)
PACKAGES: tuple[tuple[int, int], ...] = ((1000, 260), (2000, 360), (3000, 460), (5000, 560))
CUSTOM_MIN_GB = 200
CUSTOM_MAX_GB = 6000

# Request kinds and purchase-row kinds/methods.
KIND_TOPUP = "bf_topup"
KIND_SETTLEMENT = "bf_settlement"
PURCHASE_TOPUP = "topup"
PURCHASE_NEW_PANEL = "new_panel"
PURCHASE_SETTLEMENT = "settlement"
PURCHASE_INVOICE = "invoice"
# Rows that count as purchases of traffic in the stats (the rest are settlements).
PURCHASE_KINDS = (PURCHASE_TOPUP, PURCHASE_NEW_PANEL)
METHOD_CARD = "card"
METHOD_WALLET = "wallet"


def is_active() -> bool:
    """Whether the event is running right now. Never raises: this gates a menu
    button and the daily forecast, and a settings hiccup must not break either."""
    try:
        from backend.utils.settings_store import black_friday_state

        return bool(black_friday_state()["active"])
    except Exception:
        return False


# ---- pricing -------------------------------------------------------------------

def bf_price(username: str) -> float:
    """What this panel pays per GB during the event: never more than the public
    rate, and never more than their own price. With no price set at all the
    public rate applies."""
    effective = db.get_effective_price(username)
    if not effective or effective <= 0:
        return float(BF_PRICE_PER_GB)
    return min(effective, float(BF_PRICE_PER_GB))


def gift_eligible(username: str) -> bool:
    """Only someone paying more than the event rate gets the gift GB; a special
    price at or below it buys at that price and gets no gift."""
    return db.get_effective_price(username) > BF_PRICE_PER_GB


def event_rate_price(username: str) -> float | None:
    """The admin's effective price when it is above the event rate, else None
    (nothing to discount)."""
    price = db.get_effective_price(username)
    return price if price and price > BF_PRICE_PER_GB else None


@dataclass(frozen=True)
class Quote:
    paid_gb: float
    gift_gb: float
    total: int  # toman to pay
    granted_gb: float  # paid + gift
    list_total: int  # what the same GB costs at the admin's own price

    @property
    def saving(self) -> int:
        return max(0, self.list_total - self.total)


def _quote(username: str, paid_gb: float, gift_gb: float) -> Quote:
    price = bf_price(username)
    total = round(paid_gb * price)
    effective = db.get_effective_price(username)
    # No price set: nothing to compare against, so no saving is claimed.
    list_total = round(paid_gb * effective) if effective and effective > 0 else total
    return Quote(
        paid_gb=paid_gb,
        gift_gb=gift_gb,
        total=total,
        granted_gb=paid_gb + gift_gb,
        list_total=list_total,
    )


def package_quote(username: str, paid_gb: float) -> Quote | None:
    """Quote one of the fixed packages; None if `paid_gb` is not one of them."""
    for package_paid, package_gift in PACKAGES:
        if package_paid == paid_gb:
            gift = package_gift if gift_eligible(username) else 0
            return _quote(username, float(package_paid), float(gift))
    return None


def custom_quote(username: str, paid_gb: float) -> Quote | None:
    """Quote a free-form amount (no gift); None if outside the allowed range."""
    if not (CUSTOM_MIN_GB <= paid_gb <= CUSTOM_MAX_GB):
        return None
    return _quote(username, float(paid_gb), 0.0)


def requote(username: str, quote: Quote) -> Quote:
    """Today's price for the same purchase, to catch a price change between the
    invoice screen and the payment."""
    return _quote(username, quote.paid_gb, quote.gift_gb if gift_eligible(username) else 0.0)


# ---- eligibility ---------------------------------------------------------------

def has_open_bills(telegram_id: int) -> bool:
    """Anyone with a pending invoice (maintenance included) or a weekly/delayed
    debt has to settle before buying."""
    from backend.bot import bills

    return bool(bills.open_bills(telegram_id))


# ---- settling what is already owed ---------------------------------------------

def debt_parts(username: str, amount: int) -> list[tuple[int, Fraction | None]]:
    """What `amount` toman of a panel's weekly debt was priced at, per GB.

    A weekly debt only ever grows by delayed-credit sales (`weekly` rows in the
    ledger, each with its GB and money), and payments retire the oldest money
    first, so what is still owed is the newest of those sales. Walking them
    newest-first gives the real price of every toman still owed — the price on
    the day of the sale, not today's, which may be higher (that would discount
    a debt below the event rate) or lower. Anything older than the ledger is
    priced at the panel's current price, the only figure left.

    Returns [(toman, price per GB or None if unknown)].
    """
    parts: list[tuple[int, Fraction | None]] = []
    remaining = amount
    for sale in db.list_weekly_sales_for(username):
        if remaining <= 0:
            break
        if sale.amount <= 0 or not sale.gb or sale.gb <= 0:
            continue
        take = min(remaining, sale.amount)
        parts.append((take, Fraction(sale.amount) / Fraction(str(sale.gb))))
        remaining -= take
    if remaining > 0:
        current = db.get_effective_price(username)
        parts.append((remaining, Fraction(str(current)) if current and current > 0 else None))
    return parts


def _discount_parts(parts: list[tuple[int, Fraction | None]]) -> int:
    """The event-rate amount for those parts: each part priced above the rate is
    re-priced at it (rounded up); anything at or below it, or of unknown price,
    stays as it is."""
    total = 0
    for toman, price in parts:
        if price is not None and price > BF_PRICE_PER_GB:
            total += math.ceil(Fraction(toman * BF_PRICE_PER_GB) / price)
        else:
            total += toman
    return total


def debt_quote(username: str) -> tuple[int, int, int]:
    """(original, discounted, saving) for a panel's weekly/delayed debt, each
    part re-priced from what it was actually sold at (see debt_parts)."""
    original = db.get_debt(username)
    if original <= 0:
        return 0, 0, 0
    discounted = min(original, _discount_parts(debt_parts(username, original)))
    return original, discounted, original - discounted


def invoice_quote(invoice) -> tuple[int, int, int]:
    """(original, discounted, saving) for a pending invoice. Only an invoice that
    carries traffic for a panel is discounted; manual and maintenance invoices
    are shown at full amount."""
    original = invoice.amount
    if invoice.admin_username and invoice.traffic_gb and invoice.traffic_gb > 0:
        # The event caps the invoice at 2,400/GB; it never re-prices it at the
        # admin's current price, which may be lower than what was billed.
        discounted = min(original, round(invoice.traffic_gb * BF_PRICE_PER_GB))
    else:
        discounted = original
    return original, discounted, original - discounted


@dataclass
class OpenItem:
    kind: str  # "debt" | "invoice"
    ref: str  # username for a debt, invoice id for an invoice
    original: int
    discounted: int
    saving: int
    panel: str | None = None


def open_items(telegram_id: int) -> list[OpenItem]:
    """Everything this person owes, priced for the event."""
    from backend.bot import bills

    items: list[OpenItem] = []
    for bill in bills.open_bills(telegram_id):
        if bill.kind == "invoice":
            invoice = db.get_invoice(bill.invoice_id)
            if invoice is None or invoice.status != "pending":
                continue
            original, discounted, saving = invoice_quote(invoice)
            items.append(
                OpenItem("invoice", str(invoice.id), original, discounted, saving,
                         panel=invoice.admin_username)
            )
        else:
            original, discounted, saving = debt_quote(bill.username)
            if original > 0:
                items.append(OpenItem("debt", bill.username, original, discounted, saving))
    return items


def total_saving(telegram_id: int) -> int:
    return sum(item.saving for item in open_items(telegram_id))


# ---- records -------------------------------------------------------------------

def record_purchase(
    *,
    telegram_id: int | None,
    username: str | None,
    kind: str,
    paid_gb: float = 0.0,
    gift_gb: float = 0.0,
    amount: int,
    list_amount: int,
    method: str,
) -> None:
    """Write the event's own row. It only feeds the stats, so a failure here is
    logged and never undoes a payment that already went through."""
    try:
        db.insert_black_friday_purchase(
            telegram_id=telegram_id, username=username, kind=kind, paid_gb=paid_gb,
            gift_gb=gift_gb, amount=amount, list_amount=list_amount, method=method,
        )
    except Exception:
        logger.exception("could not record the black friday purchase for %s", telegram_id)


def record_discount(*, telegram_id: int | None, username: str | None, discount: int) -> None:
    """The negative ledger row that lets profit be worked out; not takings."""
    if discount > 0:
        db.record_sale(
            telegram_id=telegram_id, username=username, gb=0,
            amount=-discount, method=db.BF_DISCOUNT_METHOD,
        )


@dataclass
class DebtSettlement:
    cancelled: int  # debt actually retired
    applied: int  # money that went against it
    excess: int  # money returned to the wallet
    remaining: int  # debt still owed afterwards
    discount: int  # cancelled - applied


def settle_debt(
    telegram_id: int, username: str, paid: int, credit: int, method: str
) -> DebtSettlement:
    """Apply `paid` toman (already taken from the customer) against a debt it was
    quoted to clear in full as `credit` toman.

    The debt is read again here, not trusted from the quote: the wallet's
    auto-drain or another payment may have shrunk it since. We only retire what
    is still owed, charge pro rata for that, and put the rest of the money into
    the wallet, so the customer never loses money and the debt never goes
    negative. `credit` <= 0 means "no quote": the money is treated 1:1.
    """
    owed = db.get_debt(username)
    credit = credit if credit and credit > 0 else paid
    cancelled = min(owed, credit)
    if cancelled >= credit:
        applied = paid
    else:
        applied = min(paid, math.ceil(Fraction(cancelled * paid, credit)))
    excess = paid - applied

    remaining = db.reduce_debt(username, cancelled) if cancelled > 0 else owed
    if excess > 0:
        db.add_wallet_balance(telegram_id, excess)
    if applied > 0:
        db.record_sale(
            telegram_id=telegram_id, username=username, gb=0,
            amount=applied, method=db.SETTLEMENT_METHOD,
        )
    discount = max(0, cancelled - applied)
    if discount > 0:
        record_discount(telegram_id=telegram_id, username=username, discount=discount)
        record_purchase(
            telegram_id=telegram_id, username=username, kind=PURCHASE_SETTLEMENT,
            amount=applied, list_amount=cancelled, method=method,
        )
    return DebtSettlement(
        cancelled=cancelled, applied=applied, excess=excess,
        remaining=remaining, discount=discount,
    )


def drain_wallet_into_debt(telegram_id: int, debt: dict) -> dict | None:
    """The auto-drain for one debt while the event runs: the wallet pays the
    event-rate amount and the matching share of the original debt is retired.

    Returns {username, paid, remaining} like the normal drain, or None when the
    wallet had nothing to give. Only called for debts that are cheaper at the
    event rate; everyone else drains exactly as before."""
    username = debt["username"]
    original, needed, _ = debt_quote(username)
    if original <= 0:
        return None
    paid = db.drain_wallet(telegram_id, needed)
    if paid <= 0:
        return None
    # Paying all of the event-rate amount retires all of it; part of it retires
    # the same share of the debt, rounded up in the customer's favour only up to
    # what is owed.
    credit = original if paid >= needed else min(
        original, math.ceil(Fraction(paid * original, needed))
    )
    result = settle_debt(telegram_id, username, paid, credit, METHOD_WALLET)
    return {"username": username, "paid": paid, "remaining": result.remaining}


def has_debt_saving(username: str) -> bool:
    """Whether settling this panel's debt at the event rate costs less."""
    return debt_quote(username)[2] > 0


# ---- superadmin captions ---------------------------------------------------------

def is_bf_request(req) -> bool:
    """Whether a pending request came out of the event's flow (an invoice paid at
    the event rate carries the original amount it settles)."""
    return req.kind in (KIND_TOPUP, KIND_SETTLEMENT) or (
        req.kind == "invoice" and bool(req.bf_credit_amount)
    )


def request_caption(req) -> str:
    """What the superadmin reads above a Black Friday receipt."""
    if req.kind == KIND_TOPUP:
        paid_gb = req.bf_paid_gb if req.bf_paid_gb is not None else req.requested_gb
        return texts.BF_TOPUP_CAPTION.format(
            id=req.id, username=escape(req.admin_username or "—"),
            telegram_id=req.admin_telegram_id, paid_gb=paid_gb,
            gift_gb=req.bf_gift_gb or 0, granted_gb=req.requested_gb, total=req.toman_amount,
        )
    if req.kind == KIND_SETTLEMENT:
        return texts.BF_SETTLEMENT_CAPTION.format(
            id=req.id, username=escape(req.admin_username or "—"),
            telegram_id=req.admin_telegram_id, paid=req.toman_amount,
            credit=req.bf_credit_amount or req.toman_amount,
        )
    return texts.BF_INVOICE_CAPTION.format(
        id=req.id, invoice_id=req.invoice_id, telegram_id=req.admin_telegram_id,
        paid=req.toman_amount, credit=req.bf_credit_amount or req.toman_amount,
    )


def panel_request_caption(req: dict) -> str:
    """What the superadmin reads for a Black Friday new-panel request (a
    `panel_requests` row). Built from the stored quote, never recomputed."""
    method = texts.BF_NEW_METHOD_WALLET if req.get("paid_method") == METHOD_WALLET else texts.BF_NEW_METHOD_CARD
    paid_gb = req.get("bf_paid_gb") or 0
    gift_gb = req.get("bf_gift_gb") or 0
    return texts.BF_NEW_PANEL_CAPTION.format(
        id=req["id"], telegram_id=req["telegram_id"],
        server=escape(req.get("panel_name") or "—"),
        username=escape(req.get("desired_username") or "—"),
        paid_gb=paid_gb, gift_gb=gift_gb, granted_gb=req["traffic_gb"],
        total=req.get("bf_total") or 0, method=method,
    )


# ---- forecast ------------------------------------------------------------------

def forecast_block(telegram_id: int, username: str) -> str:
    """The Black Friday paragraph appended to a daily forecast."""
    text = texts.BF_FORECAST_BLOCK.format(price=BF_PRICE_PER_GB)
    try:
        if has_open_bills(telegram_id):
            text += texts.BF_FORECAST_DEBT
            # A saving is only worth mentioning to someone who pays more than the
            # event rate; for everyone else the settlement is just a settlement.
            if event_rate_price(username) or has_debt_saving(username):
                saving = total_saving(telegram_id)
                if saving > 0:
                    text += texts.BF_FORECAST_SAVING.format(saving=saving)
    except Exception:
        logger.exception("black friday forecast block failed for %s", telegram_id)
    return text


# ---- superadmin stats ----------------------------------------------------------

def _until_text() -> str:
    from backend.bot import sales
    from backend.utils.settings_store import black_friday_state

    ends_at = black_friday_state().get("ends_at")
    if not ends_at:
        return "—"
    try:
        end = datetime.fromisoformat(ends_at).astimezone(TEHRAN)
    except ValueError:
        return "—"
    return f"{sales.format_day(end.date())} {end:%H:%M}"


def stats_text() -> str:
    text = texts.BF_STATS_HEADER
    if is_active():
        text += texts.BF_STATS_ACTIVE.format(until=_until_text())
    else:
        text += texts.BF_STATS_INACTIVE

    rows = db.list_black_friday_purchases()
    purchases = [r for r in rows if r.kind in PURCHASE_KINDS]
    settlements = [r for r in rows if r.kind in (PURCHASE_SETTLEMENT, PURCHASE_INVOICE)]
    if not rows:
        return text + texts.BF_STATS_NONE

    purchase_discount = sum(max(0, r.list_amount - r.amount) for r in purchases)
    settlement_discount = sum(max(0, r.list_amount - r.amount) for r in settlements)
    if purchases:
        text += texts.BF_STATS_PURCHASES.format(
            count=len(purchases),
            buyers=len({r.telegram_id for r in purchases}),
            paid_gb=round(sum(r.paid_gb for r in purchases), 2),
            gift_gb=round(sum(r.gift_gb for r in purchases), 2),
            amount=sum(r.amount for r in purchases),
            discount=purchase_discount,
        )
    if settlements:
        text += texts.BF_STATS_SETTLEMENTS.format(
            count=len(settlements),
            amount=sum(r.amount for r in settlements),
            discount=settlement_discount,
        )
    text += texts.BF_STATS_MONEY.format(
        card=sum(r.amount for r in rows if r.method == METHOD_CARD),
        wallet=sum(r.amount for r in rows if r.method == METHOD_WALLET),
        discount=purchase_discount + settlement_discount,
    )

    totals: dict[int | None, dict] = {}
    for r in rows:
        entry = totals.setdefault(r.telegram_id, {"amount": 0, "name": r.username})
        entry["amount"] += r.amount
        entry["name"] = entry["name"] or r.username
    top = sorted(totals.items(), key=lambda kv: kv[1]["amount"], reverse=True)[:5]
    text += texts.BF_STATS_TOP_HEADER
    for rank, (telegram_id, entry) in enumerate(top, start=1):
        label = f"{escape(entry['name'])} ({telegram_id})" if entry["name"] else str(telegram_id)
        text += texts.BF_STATS_TOP_LINE.format(rank=rank, name=label, amount=entry["amount"])
    return text
