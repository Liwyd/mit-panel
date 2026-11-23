"""Monthly profit, worked out from the sales ledger.

Revenue is what the ledger booked: takings (everything not in db.NOT_SALES)
plus the negative `bf_discount` rows, which waive money on weekly debts that
was already booked as revenue. Cost is every GB handed out, sold or granted,
at the `cost_per_gb` setting. Months are Jalali months in Tehran time.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from backend.bot import db
from backend.bot.sales import TEHRAN, day_of, to_jalali
from backend.utils import settings_store

DEFAULT_COST_PER_GB = 1000
NO_ADMIN = "—"

JALALI_MONTHS = [
    "فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور",
    "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند",
]
_PERSIAN_DIGITS = str.maketrans("0123456789", "۰۱۲۳۴۵۶۷۸۹")


def cost_per_gb() -> float:
    try:
        value = float(settings_store.get_settings().get("cost_per_gb", DEFAULT_COST_PER_GB))
    except (TypeError, ValueError):
        return float(DEFAULT_COST_PER_GB)
    return value if value >= 0 else float(DEFAULT_COST_PER_GB)


def month_key(year: int, month: int) -> str:
    return f"{year}-{month:02d}"


def month_label(year: int, month: int) -> str:
    return f"{JALALI_MONTHS[month - 1]} {str(year).translate(_PERSIAN_DIGITS)}"


def _previous(year: int, month: int) -> tuple[int, int]:
    return (year - 1, 12) if month == 1 else (year, month - 1)


def _new_bucket() -> dict:
    return {
        "revenue": 0, "taken": 0, "discount": 0,
        "gb_sold": 0.0, "gb_free": 0.0,
        "priced_amount": 0, "priced_gb": 0.0,
        "unknown_gb_revenue": 0,
    }


def _add(bucket: dict, sale) -> None:
    if sale.method == db.BF_DISCOUNT_METHOD:
        bucket["revenue"] += sale.amount
        bucket["discount"] -= sale.amount
    elif sale.method == db.GRANT_METHOD:
        bucket["gb_free"] += sale.gb
    elif sale.method not in db.NOT_SALES:
        bucket["revenue"] += sale.amount
        bucket["taken"] += sale.amount
        bucket["gb_sold"] += sale.gb
        if sale.gb > 0:
            bucket["priced_amount"] += sale.amount
            bucket["priced_gb"] += sale.gb
        else:
            bucket["unknown_gb_revenue"] += sale.amount


def _figures(bucket: dict, unit_cost: float) -> dict:
    cost = round((bucket["gb_sold"] + bucket["gb_free"]) * unit_cost)
    revenue = bucket["revenue"]
    profit = revenue - cost
    return {
        "revenue": revenue,
        "cost": cost,
        "profit": profit,
        "margin": profit / revenue if revenue > 0 else None,
        "gb_sold": round(bucket["gb_sold"], 2),
        "gb_free": round(bucket["gb_free"], 2),
        "avg_price_per_gb": (
            bucket["priced_amount"] / bucket["priced_gb"] if bucket["priced_gb"] > 0 else None
        ),
        "unknown_gb_revenue": bucket["unknown_gb_revenue"],
        "bf_discount": bucket["discount"],
    }


def monthly_report(months: int = 6, now: datetime | None = None) -> dict:
    """The last `months` Jalali months, newest first, empty ones included."""
    months = max(1, int(months))
    now = now or datetime.now(TEHRAN)
    unit_cost = cost_per_gb()
    today = now.astimezone(TEHRAN)
    year, month, _ = to_jalali(today.year, today.month, today.day)

    wanted: list[tuple[int, int]] = []
    for _ in range(months):
        wanted.append((year, month))
        year, month = _previous(year, month)
    wanted_keys = {month_key(*ym) for ym in wanted}

    # Generous lower bound; rows outside the wanted months are dropped below.
    since = (today - timedelta(days=31 * months + 31)).astimezone(timezone.utc).isoformat()
    totals = {key: _new_bucket() for key in wanted_keys}
    admins: dict[str, dict[str, dict]] = {key: {} for key in wanted_keys}
    for sale in db.list_sales_since(since):
        day = day_of(sale.created_at)
        if day is None:
            continue
        key = month_key(*to_jalali(day.year, day.month, day.day)[:2])
        if key not in wanted_keys:
            continue
        _add(totals[key], sale)
        _add(admins[key].setdefault(sale.username or NO_ADMIN, _new_bucket()), sale)

    result = []
    for year, month in wanted:
        key = month_key(year, month)
        per_admin = []
        for name, bucket in admins[key].items():
            figures = _figures(bucket, unit_cost)
            per_admin.append({
                "username": name,
                **{k: figures[k] for k in (
                    "revenue", "gb_sold", "gb_free", "avg_price_per_gb", "cost", "profit"
                )},
            })
        per_admin.sort(key=lambda row: row["profit"], reverse=True)
        result.append({
            "key": key,
            "label_fa": month_label(year, month),
            **_figures(totals[key], unit_cost),
            "per_admin": per_admin,
        })
    return {"cost_per_gb": unit_cost, "months": result}


def black_friday_summary() -> dict:
    """How the Black Friday event did, on its own.

    Event profit = money taken by top-up purchases - discount waived on
    settled weekly debts - cost of the GB those purchases handed out (paid +
    gift). A settlement's money is not new revenue (the weekly sale was booked
    in full when it was made); only what it waived reduces profit. Paid
    invoices are left out of profit: their purchase row records no GB, so
    their revenue could not be costed."""
    unit_cost = cost_per_gb()
    rows = db.list_black_friday_purchases()
    # Same split as the bot's own stats: top-ups are purchases; settled debts
    # and paid invoices are "settlements".
    purchases = [r for r in rows if r.kind in ("topup", "new_panel")]
    settlements = [r for r in rows if r.kind in ("settlement", "invoice")]
    waived = [r for r in rows if r.kind == "settlement"]
    amount = sum(r.amount for r in purchases)
    paid_gb = sum(r.paid_gb for r in purchases)
    gift_gb = sum(r.gift_gb for r in purchases)
    waived_amount = sum(max(0, r.list_amount - r.amount) for r in waived)
    cost = round((paid_gb + gift_gb) * unit_cost)
    buyers = {r.telegram_id if r.telegram_id is not None else r.username for r in rows}
    state = settings_store.black_friday_state()
    return {
        "active": state["active"],
        "ends_at": state["ends_at"],
        "purchases": len(purchases),
        "buyers": len(buyers),
        "paid_gb": round(paid_gb, 2),
        "gift_gb": round(gift_gb, 2),
        "amount": amount,
        "discount": sum(max(0, r.list_amount - r.amount) for r in purchases),
        "settlements": len(settlements),
        "settlements_amount": sum(r.amount for r in settlements),
        "settlements_discount": sum(max(0, r.list_amount - r.amount) for r in settlements),
        "card_amount": sum(r.amount for r in rows if r.method == "card"),
        "wallet_amount": sum(r.amount for r in rows if r.method == "wallet"),
        "cost": cost,
        "profit": amount - waived_amount - cost,
    }
