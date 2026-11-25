"""Monthly profit, worked out from the sales ledger.

Revenue is what the ledger booked: takings (everything not in db.NOT_SALES)
plus the negative `bf_discount` rows, which waive money on weekly debts that
was already booked as revenue. Cost is every GB handed out, sold or granted,
at `credit_cost_per_gb()`: the `cost_per_gb` setting divided by the
`traffic_multiplier` setting, since with a multiplier of 1.4 a GB of credit is
only 1 / 1.4 GB of real traffic. Months are Jalali months in Tehran time.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone

from backend.bot import bills, db
from backend.bot.sales import TEHRAN, day_of, jalali_month_length, to_gregorian, to_jalali
from backend.db.engin import sessionLocal
from backend.utils import settings_store

logger = logging.getLogger(__name__)

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


def traffic_multiplier() -> float:
    """How much credit 1 unit of real traffic uses up (1.4 → 1 MB used costs
    1.4 MB of credit). Anything missing or unusable reads as 1, i.e. no
    multiplier — never 0, which would divide by zero."""
    try:
        value = float(settings_store.get_settings().get("traffic_multiplier", 1) or 1)
    except (TypeError, ValueError):
        return 1.0
    return value if 0.1 <= value <= 10 else 1.0


def credit_cost_per_gb() -> float:
    """What one GB of credit (what is sold and granted) really costs."""
    return cost_per_gb() / traffic_multiplier()


def _amount_setting(name: str) -> float:
    """A toman setting that defaults to 0; anything unusable reads as 0."""
    try:
        value = float(settings_store.get_settings().get(name, 0) or 0)
    except (TypeError, ValueError):
        return 0.0
    return value if value >= 0 else 0.0


def fixed_monthly_cost() -> float:
    return _amount_setting("fixed_monthly_cost")


def monthly_revenue_target() -> float:
    return _amount_setting("monthly_revenue_target")


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


def _admin_rows(buckets: dict[str, dict], unit_cost: float, total_revenue: int) -> list[dict]:
    """One row per panel, most profitable first. `margin` is profit / the
    panel's revenue; `share` is its revenue / the month's total revenue."""
    rows = []
    for name, bucket in buckets.items():
        figures = _figures(bucket, unit_cost)
        rows.append({
            "username": name,
            **{k: figures[k] for k in (
                "revenue", "gb_sold", "gb_free", "avg_price_per_gb", "cost", "profit", "margin"
            )},
            "share": figures["revenue"] / total_revenue if total_revenue > 0 else None,
        })
    rows.sort(key=lambda row: row["profit"], reverse=True)
    return rows


def _wanted_months(months: int, now: datetime | None) -> tuple[datetime, list[tuple[int, int]]]:
    """The current Jalali month and the `months - 1` before it, newest first."""
    today = (now or datetime.now(TEHRAN)).astimezone(TEHRAN)
    year, month, _ = to_jalali(today.year, today.month, today.day)
    wanted: list[tuple[int, int]] = []
    for _ in range(months):
        wanted.append((year, month))
        year, month = _previous(year, month)
    return today, wanted


def monthly_report(months: int = 6, now: datetime | None = None) -> dict:
    """The last `months` Jalali months, newest first, empty ones included."""
    months = max(1, int(months))
    unit_cost = credit_cost_per_gb()
    today, wanted = _wanted_months(months, now)
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
        result.append({
            "key": key,
            "label_fa": month_label(year, month),
            **_figures(totals[key], unit_cost),
            "per_admin": _admin_rows(admins[key], unit_cost, totals[key]["revenue"]),
        })
    return {
        "cost_per_gb": cost_per_gb(),
        "traffic_multiplier": traffic_multiplier(),
        "cost_per_credit_gb": unit_cost,
        "months": result,
    }


def black_friday_summary() -> dict:
    """How the Black Friday event did, on its own.

    Event profit = money taken by top-up purchases - discount waived on
    settled weekly debts - cost of the GB those purchases handed out (paid +
    gift). A settlement's money is not new revenue (the weekly sale was booked
    in full when it was made); only what it waived reduces profit. Paid
    invoices are left out of profit: their purchase row records no GB, so
    their revenue could not be costed."""
    unit_cost = credit_cost_per_gb()
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


# ---------------------------------------------------------------------------
# The profit page: everything below is read-only analytics over the same ledger
# and the same accounting as monthly_report (takings = methods outside
# db.NOT_SALES, bf_discount rows reduce revenue, grants are cost without
# revenue, cost = GB x cost_per_gb).
# ---------------------------------------------------------------------------

_MONTH_KEY = re.compile(r"^(\d{4})-(0[1-9]|1[0-2])$")

# Payment-method buckets, in no particular order (the result is sorted by
# amount). A method that is in none of them lands in "other".
METHOD_BUCKETS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("card", "کارت به کارت", ("card",)),
    ("wallet", "کیف پول", ("wallet",)),
    ("weekly", "اعتباری/پرداخت با تاخیر", ("weekly",)),
    ("invoice", "فاکتور", ("invoice",)),
    ("shop", "خرید پنل جدید", ("shop",)),
    ("black_friday", "بلک‌فرایدی", (db.BF_CARD_METHOD, db.BF_WALLET_METHOD)),
)
OTHER_METHOD = ("other", "سایر")

# Price-per-GB bands. Every band includes its lower edge and excludes its upper
# edge, so a sale at exactly 2,400 toman/GB is in the "2,400 to 2,700" band and
# one at exactly 3,000 is in the top band.
PRICE_BANDS: tuple[tuple[str, str, int | None, int | None], ...] = (
    ("lt2000", "زیر ۲٬۰۰۰", None, 2000),
    ("2000", "۲٬۰۰۰ تا ۲٬۴۰۰", 2000, 2400),
    ("2400", "۲٬۴۰۰ تا ۲٬۷۰۰", 2400, 2700),
    ("2700", "۲٬۷۰۰ تا ۳٬۰۰۰", 2700, 3000),
    ("3000", "بالای ۳٬۰۰۰", 3000, None),
)

# Overdue buckets for open bills. A bill that is late by under a day (days
# overdue 0) is in "1 to 7"; 7 is the last day of that band, 8 the first of
# the next, 30 the last of "8 to 30" and 31 the first of "over 30".
AGING_BUCKETS: tuple[tuple[str, str], ...] = (
    ("current", "جاری"),
    ("d1_7", "۱ تا ۷ روز"),
    ("d8_30", "۸ تا ۳۰ روز"),
    ("d30_plus", "بیش از ۳۰ روز"),
)

GIB = 1024 ** 3
TOP_USAGE_PANELS = 5


def parse_month_key(key: str) -> tuple[int, int]:
    match = _MONTH_KEY.match(key or "")
    if not match:
        raise ValueError(f"bad month key: {key!r}")
    return int(match.group(1)), int(match.group(2))


@dataclass
class _Row:
    sale: object
    year: int
    month: int
    day: int

    @property
    def key(self) -> str:
        return month_key(self.year, self.month)

    @property
    def is_taking(self) -> bool:
        return self.sale.method not in db.NOT_SALES

    @property
    def panel(self) -> str | None:
        """The panel a takings row belongs to; rows with no panel are not buyers."""
        return self.sale.username or None


def _rows(sales) -> list[_Row]:
    rows = []
    for sale in sales:
        day = day_of(sale.created_at)
        if day is None:
            continue
        year, month, date = to_jalali(day.year, day.month, day.day)
        rows.append(_Row(sale, year, month, date))
    return rows


def _safe(section: str, build):
    """A section that fails is logged and reported as null, never raised."""
    try:
        return build()
    except Exception:
        logger.exception("Profit overview section %r failed", section)
        return None


def _share(part: float, whole: float) -> float | None:
    return part / whole if whole > 0 else None


def _month_figures(bucket: dict, unit_cost: float, fixed: float) -> dict:
    figures = _figures(bucket, unit_cost)
    figures["fixed_cost"] = round(fixed)
    figures["net_profit"] = figures["profit"] - round(fixed)
    return figures


def _buyer_stats(rows: list[_Row]) -> tuple[dict[str, set], dict[str, str]]:
    """Panels with takings per month key, and each panel's first month key."""
    active: dict[str, set] = {}
    first: dict[str, str] = {}
    for row in rows:
        if not row.is_taking or row.panel is None:
            continue
        active.setdefault(row.key, set()).add(row.panel)
        if row.panel not in first or row.key < first[row.panel]:
            first[row.panel] = row.key
    return active, first


def _daily(rows: list[_Row], year: int, month: int, today: tuple[int, int, int]) -> list[dict]:
    length = jalali_month_length(year, month)
    days = [{"day": d, "revenue": 0, "gb_sold": 0.0} for d in range(1, length + 1)]
    for row in rows:
        if (row.year, row.month) != (year, month) or not 1 <= row.day <= length:
            continue
        bucket = _new_bucket()
        _add(bucket, row.sale)
        days[row.day - 1]["revenue"] += bucket["revenue"]
        days[row.day - 1]["gb_sold"] += bucket["gb_sold"]
    for entry in days:
        entry["gb_sold"] = round(entry["gb_sold"], 2)
        entry["future"] = (year, month, entry["day"]) > today
        g = to_gregorian(year, month, entry["day"])
        entry["date"] = f"{g[0]}-{g[1]:02d}-{g[2]:02d}"
    return days


def _by_method(rows: list[_Row], year: int, month: int) -> list[dict]:
    """Takings of the month per payment method, biggest first. bf_discount
    rows are not takings and are not in here, so the shares add up to 100% of
    what was taken, not of revenue."""
    lookup = {m: (key, label) for key, label, methods in METHOD_BUCKETS for m in methods}
    totals: dict[str, dict] = {}
    for row in rows:
        if (row.year, row.month) != (year, month) or not row.is_taking:
            continue
        key, label = lookup.get(row.sale.method, OTHER_METHOD)
        entry = totals.setdefault(key, {"key": key, "label": label, "amount": 0, "count": 0})
        entry["amount"] += row.sale.amount
        entry["count"] += 1
    taken = sum(e["amount"] for e in totals.values())
    result = sorted(totals.values(), key=lambda e: e["amount"], reverse=True)
    for entry in result:
        entry["share"] = _share(entry["amount"], taken)
    return result


def _price_band(amount: int, gb: float) -> str:
    """Band key of one sale. Compared as amount >= edge * gb rather than a
    divided price, so a sale at exactly an edge is never pushed below it by
    float rounding."""
    chosen = PRICE_BANDS[0][0]
    for key, _label, low, _high in PRICE_BANDS:
        if low is None or amount >= low * gb:
            chosen = key
    return chosen


def _price_bands(rows: list[_Row], year: int, month: int) -> list[dict]:
    bands = {
        key: {"key": key, "label": label, "min": low, "max": high,
              "gb": 0.0, "revenue": 0, "rows": 0}
        for key, label, low, high in PRICE_BANDS
    }
    for row in rows:
        sale = row.sale
        if (row.year, row.month) != (year, month) or not row.is_taking or sale.gb <= 0:
            continue
        band = bands[_price_band(sale.amount, sale.gb)]
        band["gb"] += sale.gb
        band["revenue"] += sale.amount
        band["rows"] += 1
    for band in bands.values():
        band["gb"] = round(band["gb"], 2)
    return list(bands.values())


def _concentration(per_admin: list[dict], total_revenue: int) -> dict:
    """Share of the month's revenue from the biggest panels, ranked by revenue
    (panels only: rows with no panel count in the total, not in the ranking)."""
    ranked = sorted(
        (r for r in per_admin if r["username"] != NO_ADMIN),
        key=lambda r: r["revenue"], reverse=True,
    )
    top = sum(r["revenue"] for r in ranked[:1])
    top5 = sum(r["revenue"] for r in ranked[:5])
    return {
        "top1_share": _share(top, total_revenue),
        "top5_share": _share(top5, total_revenue),
        "top1_username": ranked[0]["username"] if ranked else None,
    }


def _month_window_utc(year: int, month: int) -> tuple[datetime, datetime]:
    """Naive-UTC start and end of a Jalali month, which begins at Tehran midnight."""
    start = datetime(*to_gregorian(year, month, 1), tzinfo=TEHRAN)
    next_year, next_month = (year + 1, 1) if month == 12 else (year, month + 1)
    end = datetime(*to_gregorian(next_year, next_month, 1), tzinfo=TEHRAN)
    utc = timezone.utc
    return (
        start.astimezone(utc).replace(tzinfo=None),
        end.astimezone(utc).replace(tzinfo=None),
    )


def _consumption(year: int, month: int, gb_sold: float) -> dict | None:
    """What end users really used in the month, from the Analytics usage log
    (admin_usage_hourly, hours stored as naive UTC). Null when the table is
    missing or has no hours in the month."""
    from sqlalchemy import func, inspect

    from backend.db.model import Admins, AdminUsageHourly

    start, end = _month_window_utc(year, month)
    with sessionLocal() as session:
        if not inspect(session.get_bind()).has_table(AdminUsageHourly.__tablename__):
            return None
        per_admin = (
            session.query(AdminUsageHourly.admin_id, func.sum(AdminUsageHourly.used))
            .filter(AdminUsageHourly.hour >= start, AdminUsageHourly.hour < end)
            .group_by(AdminUsageHourly.admin_id)
            .all()
        )
        if not per_admin:
            return None
        ids = [admin_id for admin_id, _ in per_admin]
        names = {
            row.id: row.username
            for row in session.query(Admins.id, Admins.username).filter(Admins.id.in_(ids))
        }
    used = {admin_id: (total or 0) / GIB for admin_id, total in per_admin}
    total_gb = sum(used.values())
    top = sorted(used.items(), key=lambda kv: kv[1], reverse=True)[:TOP_USAGE_PANELS]
    return {
        "used_gb": round(total_gb, 2),
        "use_to_sold": _share(total_gb, gb_sold),
        "top_panels": [
            {
                "username": names.get(admin_id, f"#{admin_id}"),
                "used_gb": round(gb, 2),
                "share": _share(gb, total_gb),
            }
            for admin_id, gb in top
        ],
    }


def receivables(now: datetime | None = None) -> dict:
    """What customers owe and hold, right now (not per month).

    Debts and invoices come from bills.open_bills, so they are totalled and
    dated exactly as the bot's own debt screens do: only pending invoices
    (paid and cancelled are out) and weekly debts above zero. A bill is
    "current" until its due date, then ages by whole days late. Wallet money
    is held on behalf of customers, a liability until they spend it.

    There is deliberately no "cash position": the ledger records takings but
    not money paid out or what is sitting in the bank, so any figure here
    would pass for cash the business does not necessarily have."""
    now = (now or datetime.now(TEHRAN)).astimezone(TEHRAN)
    open_ = bills.open_bills(now=now)
    aging = {key: {"key": key, "label": label, "amount": 0, "count": 0}
             for key, label in AGING_BUCKETS}
    for bill in open_:
        late = bill.days_overdue(now)
        if late is None:
            key = "current"
        elif late <= 7:
            key = "d1_7"
        elif late <= 30:
            key = "d8_30"
        else:
            key = "d30_plus"
        aging[key]["amount"] += bill.amount
        aging[key]["count"] += 1
    debts = [b for b in open_ if b.kind == "weekly"]
    invoices = [b for b in open_ if b.kind == "invoice"]
    wallet_total, wallet_count = db.wallet_totals()
    return {
        "debts_total": sum(b.amount for b in debts),
        "debts_count": len(debts),
        "invoices_total": sum(b.amount for b in invoices),
        "invoices_count": len(invoices),
        "total": sum(b.amount for b in open_),
        "aging": list(aging.values()),
        "wallet_total": wallet_total,
        "wallet_count": wallet_count,
    }


def _selected(
    rows: list[_Row], key: str, today: datetime, current_key: str, settings: dict,
    fixed_for: dict[str, float], unit_cost: float, buyers: dict, previous_key: str,
) -> dict:
    """The selected month in depth. `buyers` is {"active": {key: panels},
    "first": {panel: first month key}}."""
    year, month = parse_month_key(key)
    in_month = [r for r in rows if r.key == key]
    totals = _new_bucket()
    admins: dict[str, dict] = {}
    for row in in_month:
        _add(totals, row.sale)
        _add(admins.setdefault(row.sale.username or NO_ADMIN, _new_bucket()), row.sale)

    fixed = fixed_for.get(key, 0)
    figures = _month_figures(totals, unit_cost, fixed)
    per_admin = _admin_rows(admins, unit_cost, figures["revenue"])
    here = buyers["active"].get(key, set())
    active = len(here)

    prev_totals = _new_bucket()
    for row in rows:
        if row.key == previous_key:
            _add(prev_totals, row.sale)
    previous = _month_figures(prev_totals, unit_cost, fixed_for.get(previous_key, 0))
    previous["key"] = previous_key
    previous["label_fa"] = month_label(*parse_month_key(previous_key))

    today_j = to_jalali(today.year, today.month, today.day)
    target = settings["monthly_revenue_target"]
    avg_price = figures["avg_price_per_gb"]
    margin_per_gb = avg_price - unit_cost if avg_price is not None else None
    break_even = None
    break_even_reached = None
    if margin_per_gb is not None and margin_per_gb > 0:
        break_even = round(settings["fixed_monthly_cost"] / margin_per_gb, 2)
        break_even_reached = figures["gb_sold"] >= break_even

    result = {
        "key": key,
        "label_fa": month_label(year, month),
        "is_current": key == current_key,
        **figures,
        "previous": previous,
        "active_buyers": active,
        "new_buyers": sum(1 for first in buyers["first"].values() if first == key),
        "lost_buyers": len(buyers["active"].get(previous_key, set()) - here),
        "arpu": _share(figures["revenue"], active) if active else None,
        "net_profit_per_gb": (
            figures["net_profit"] / figures["gb_sold"] if figures["gb_sold"] > 0 else None
        ),
        "target": (
            {"amount": target, "progress": figures["revenue"] / target} if target > 0 else None
        ),
        "break_even_gb": break_even,
        "break_even_reached": break_even_reached,
        "per_admin": per_admin,
        "concentration": _safe(
            "concentration", lambda: _concentration(per_admin, figures["revenue"])
        ),
        "daily": _safe("daily", lambda: _daily(rows, year, month, today_j)),
        "by_method": _safe("by_method", lambda: _by_method(rows, year, month)),
        "price_bands": _safe("price_bands", lambda: _price_bands(rows, year, month)),
        "forecast": None,
        "consumption": _safe(
            "consumption", lambda: _consumption(year, month, figures["gb_sold"])
        ),
    }
    if key == current_key:
        result["forecast"] = _safe(
            "forecast", lambda: _forecast(figures, today_j, year, month, target, fixed)
        )
    return result


def _forecast(figures: dict, today_j, year: int, month: int, target: float, fixed: float) -> dict:
    """Run-rate projection: month-to-date / days elapsed x days in the month.
    Today counts as elapsed (a partial day, so early in the day this projects
    low). Cost scales the same way because it follows GB sold; fixed cost is
    already a whole-month figure and is not scaled."""
    total_days = jalali_month_length(year, month)
    elapsed = max(1, min(today_j[2], total_days))
    scale = total_days / elapsed
    projected_revenue = round(figures["revenue"] * scale)
    projected_cost = round(figures["cost"] * scale)
    projected_profit = projected_revenue - projected_cost
    return {
        "month_to_date": figures["revenue"],
        "days_elapsed": elapsed,
        "days_total": total_days,
        "days_left": total_days - elapsed,
        "projected_revenue": projected_revenue,
        "projected_cost": projected_cost,
        "projected_profit": projected_profit,
        "projected_net_profit": projected_profit - round(fixed),
        "target_progress": figures["revenue"] / target if target > 0 else None,
        "projected_target_progress": projected_revenue / target if target > 0 else None,
    }


def overview(
    months: int = 12, month_key: str | None = None, now: datetime | None = None
) -> dict:
    """Everything the profit page shows, in one call.

    `months` newest-first figures for the range, a deep look at the selected
    month (default: the current Jalali month), receivables and the Black
    Friday summary. Each section is built on its own: one that raises is logged
    and comes back null, the rest still arrive.

    Added on top of monthly_report's figures per month: `fixed_cost` (the
    fixed_monthly_cost setting, charged from the first month with any takings,
    so months before the business began are not shown as losses),
    `net_profit` = profit - fixed_cost, and buyer counts (a buyer is a panel
    with takings; rows with no panel are not counted): `active_buyers`,
    `new_buyers` (first takings ever fall in that month) and `lost_buyers`
    (took in the previous month, nothing in this one; for the running month
    this reads high early on because the month is not over)."""
    months = max(1, min(int(months), 24))
    now = (now or datetime.now(TEHRAN)).astimezone(TEHRAN)
    today, wanted = _wanted_months(months, now)
    current_key = month_key_of(wanted[0])
    selected_key = month_key or current_key
    parse_month_key(selected_key)  # ValueError on a malformed key
    unit_cost = credit_cost_per_gb()
    settings = {
        # As configured, so the settings form shows what was saved; the figures
        # use cost_per_credit_gb.
        "cost_per_gb": cost_per_gb(),
        "traffic_multiplier": traffic_multiplier(),
        "cost_per_credit_gb": unit_cost,
        "fixed_monthly_cost": fixed_monthly_cost(),
        "monthly_revenue_target": monthly_revenue_target(),
    }

    # The whole ledger: "first ever purchase" needs every row, and the volume
    # of a reseller's sales is small.
    rows = _safe("ledger", lambda: _rows(db.list_sales_since("")))
    result: dict = {"settings": settings, "months": None, "selected": None}
    if rows is not None:
        buyers_active, buyers_first = _buyer_stats(rows)
        new_per_month: dict[str, int] = {}
        for first in buyers_first.values():
            new_per_month[first] = new_per_month.get(first, 0) + 1
        first_month = min(buyers_first.values(), default=None)
        keys = [month_key_of(ym) for ym in wanted]

        fixed_for: dict[str, float] = {}
        for key in {*keys, selected_key, previous_key_of(selected_key)}:
            on = first_month is not None and key >= first_month
            fixed_for[key] = settings["fixed_monthly_cost"] if on else 0

        def build_months() -> list[dict]:
            totals = {key: _new_bucket() for key in keys}
            for row in rows:
                if row.key in totals:
                    _add(totals[row.key], row.sale)
            out = []
            for (year, month), key in zip(wanted, keys):
                prev = month_key_of(_previous(year, month))
                here = buyers_active.get(key, set())
                out.append({
                    "key": key,
                    "label_fa": month_label(year, month),
                    **_month_figures(totals[key], unit_cost, fixed_for[key]),
                    "active_buyers": len(here),
                    "new_buyers": new_per_month.get(key, 0),
                    "lost_buyers": len(buyers_active.get(prev, set()) - here),
                })
            return out

        result["months"] = _safe("months", build_months)
        result["selected"] = _safe(
            "selected",
            lambda: _selected(
                rows, selected_key, today, current_key, settings, fixed_for, unit_cost,
                {"active": buyers_active, "first": buyers_first}, previous_key_of(selected_key),
            ),
        )
    result["receivables"] = _safe("receivables", lambda: receivables(now))
    result["black_friday"] = _safe("black_friday", black_friday_summary)
    return result


def month_key_of(ym: tuple[int, int]) -> str:
    return month_key(*ym)


def previous_key_of(key: str) -> str:
    return month_key_of(_previous(*parse_month_key(key)))
