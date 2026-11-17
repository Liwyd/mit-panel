"""What the admin's Analytics page shows: their users' usage hour by hour and
day by day, which Marzban nodes those users use most, and how fast the admin
sells traffic: a daily average over the last week (which also gives the days
left until the balance runs out) and a forecast for tomorrow from the last 24
hours.

Usage comes from AdminUsageHourly, which the usage recorder fills while it
reads users anyway; sales from AdminTrafficLog, written wherever the balance is
charged or refunded. Only the node ranking asks Marzban itself, with the
panel's own login (cached), and that answer is kept for a couple of minutes.
"""

import asyncio
import time
from datetime import datetime, timedelta

from sqlalchemy import func
from sqlalchemy.orm import Session

from backend.config import config
from backend.db.model import Admins, AdminTrafficLog, AdminUsageHourly

# The daily sales average (and the days left) covers this many days back from
# now; tomorrow's forecast is the sales of the last TOMORROW_WINDOW_HOURS.
SALES_WINDOW_DAYS = 7
TOMORROW_WINDOW_HOURS = 24
# History kept; older rows are pruned by the usage recorder loop.
RETENTION_DAYS = 90
HOURS_SHOWN = 24
DAYS_SHOWN = 7

NODE_PERIODS: dict[str, timedelta] = {
    "1d": timedelta(days=1),
    "7d": timedelta(days=7),
    "30d": timedelta(days=30),
}
_NODE_CACHE_TTL = 120
_node_cache: dict[tuple[int, str], tuple[float, list[dict]]] = {}


def _offset() -> timedelta:
    return timedelta(minutes=config.ANALYTICS_UTC_OFFSET_MINUTES)


def local(at: datetime) -> datetime:
    return at + _offset()


def hour_start(at: datetime) -> datetime:
    """Start of the local hour `at` (naive UTC) falls in, as naive UTC."""
    return local(at).replace(minute=0, second=0, microsecond=0) - _offset()


def day_start(at: datetime) -> datetime:
    """Start of the local day `at` (naive UTC) falls in, as naive UTC."""
    return local(at).replace(hour=0, minute=0, second=0, microsecond=0) - _offset()


def record_usage(db: Session, admin_id: int, used: int, at: datetime) -> None:
    """Add traffic an admin's users used to the hour it was seen in. The
    caller commits."""
    if used <= 0:
        return
    hour = hour_start(at)
    updated = (
        db.query(AdminUsageHourly)
        .filter(AdminUsageHourly.admin_id == admin_id, AdminUsageHourly.hour == hour)
        .update({AdminUsageHourly.used: AdminUsageHourly.used + used}, synchronize_session=False)
    )
    if not updated:
        db.add(AdminUsageHourly(admin_id=admin_id, hour=hour, used=used))
        # Flushed now so a second record for the same hour in this session
        # finds the row instead of adding a duplicate.
        db.flush()


def sales_backfilled(db: Session, admin_id: int) -> bool:
    return (
        db.query(AdminTrafficLog.id)
        .filter(AdminTrafficLog.admin_id == admin_id, AdminTrafficLog.kind == "backfill")
        .first()
        is not None
    )


def sales_log_start(db: Session, admin_id: int) -> datetime | None:
    """When the first sale was logged (backfill aside)."""
    return (
        db.query(func.min(AdminTrafficLog.created_at))
        .filter(AdminTrafficLog.admin_id == admin_id, AdminTrafficLog.kind != "backfill")
        .scalar()
    )


def prune(db: Session, now: datetime | None = None) -> None:
    cutoff = (now or datetime.utcnow()) - timedelta(days=RETENTION_DAYS)
    db.query(AdminUsageHourly).filter(AdminUsageHourly.hour < cutoff).delete(synchronize_session=False)
    # The 0-sized backfill markers stay, or the backfill would run again.
    db.query(AdminTrafficLog).filter(
        AdminTrafficLog.created_at < cutoff, AdminTrafficLog.amount != 0
    ).delete(synchronize_session=False)
    db.commit()


def _usage(db: Session, admin_id: int, now: datetime) -> dict:
    first_hour = hour_start(now) - timedelta(hours=HOURS_SHOWN - 1)
    first_day = day_start(now) - timedelta(days=DAYS_SHOWN - 1)
    rows = (
        db.query(AdminUsageHourly.hour, AdminUsageHourly.used)
        .filter(AdminUsageHourly.admin_id == admin_id, AdminUsageHourly.hour >= min(first_hour, first_day))
        .all()
    )
    by_hour: dict[datetime, int] = {}
    by_day: dict[datetime, int] = {}
    for hour, used in rows:
        by_hour[hour] = by_hour.get(hour, 0) + int(used)
        day = day_start(hour)
        by_day[day] = by_day.get(day, 0) + int(used)

    hourly = []
    for i in range(HOURS_SHOWN):
        hour = first_hour + timedelta(hours=i)
        hourly.append({"start": hour.isoformat(), "label": local(hour).strftime("%H:00"), "used": by_hour.get(hour, 0)})
    daily = []
    for i in range(DAYS_SHOWN):
        day = first_day + timedelta(days=i)
        daily.append({"start": day.isoformat(), "date": local(day).strftime("%Y-%m-%d"), "used": by_day.get(day, 0)})

    since = (
        db.query(func.min(AdminUsageHourly.hour)).filter(AdminUsageHourly.admin_id == admin_id).scalar()
    )
    return {
        "today": daily[-1]["used"],
        "yesterday": daily[-2]["used"],
        "hourly": hourly,
        "daily": daily,
        "since": since.isoformat() if since else None,
    }


def _sales(db: Session, admin: Admins, now: datetime) -> dict:
    first_day = day_start(now) - timedelta(days=DAYS_SHOWN - 1)
    window_start = now - timedelta(days=SALES_WINDOW_DAYS)
    tomorrow_start = now - timedelta(hours=TOMORROW_WINDOW_HOURS)
    rows = (
        db.query(AdminTrafficLog.created_at, AdminTrafficLog.amount)
        .filter(
            AdminTrafficLog.admin_id == admin.id,
            AdminTrafficLog.created_at >= min(first_day, window_start),
        )
        .all()
    )
    by_day: dict[datetime, int] = {}
    window_total = 0
    last_24h = 0
    for created_at, amount in rows:
        day = day_start(created_at)
        by_day[day] = by_day.get(day, 0) + int(amount)
        if created_at >= window_start:
            window_total += int(amount)
        if created_at >= tomorrow_start:
            last_24h += int(amount)

    daily = []
    for i in range(DAYS_SHOWN):
        day = first_day + timedelta(days=i)
        daily.append({"start": day.isoformat(), "date": local(day).strftime("%Y-%m-%d"), "sold": by_day.get(day, 0)})

    # Refunds can outweigh charges for a while; a negative rate means nothing
    # for the forecast, so it counts as no sales.
    per_day = max(window_total, 0) / SALES_WINDOW_DAYS
    remaining = int(admin.traffic or 0)
    if remaining <= 0:
        days_left = 0.0
    elif per_day > 0:
        days_left = remaining / per_day
    else:
        days_left = None  # No sales lately: the balance isn't running down.

    # How far back the log really reaches: the earlier sales read from
    # Marzban cover DAYS_SHOWN days before the backfill ran, sales or not.
    backfilled_at = (
        db.query(func.min(AdminTrafficLog.created_at))
        .filter(
            AdminTrafficLog.admin_id == admin.id,
            AdminTrafficLog.kind == "backfill",
            AdminTrafficLog.amount == 0,
        )
        .scalar()
    )
    started = (
        backfilled_at - timedelta(days=DAYS_SHOWN)
        if backfilled_at
        else db.query(func.min(AdminTrafficLog.created_at))
        .filter(AdminTrafficLog.admin_id == admin.id, AdminTrafficLog.amount != 0)
        .scalar()
    )
    covered = (now - started).total_seconds() / 86400 if started else 0.0

    return {
        "daily": daily,
        "window_days": SALES_WINDOW_DAYS,
        "window_total": window_total,
        "per_day": int(per_day),
        "tomorrow": max(last_24h, 0),
        "tomorrow_window_hours": TOMORROW_WINDOW_HOURS,
        "days_left": round(days_left, 1) if days_left is not None else None,
        "runs_out_at": (now + timedelta(days=days_left)).isoformat() if days_left else None,
        # Less than the full window behind the average: say so on the page.
        "days_covered": round(min(covered, SALES_WINDOW_DAYS), 1),
    }


def build_admin_analytics(db: Session, admin: Admins, now: datetime | None = None) -> dict:
    now = now or datetime.utcnow()
    return {
        "generated_at": now.isoformat(),
        "utc_offset_minutes": config.ANALYTICS_UTC_OFFSET_MINUTES,
        "remaining": int(admin.traffic or 0),
        "initial": int(admin.initial_traffic or 0),
        "usage": _usage(db, admin.id, now),
        "sales": _sales(db, admin, now),
    }


def node_key(node_id) -> str:
    """How node names are keyed in settings: Marzban's id, or "master" for
    the main server (which Marzban reports with no id)."""
    return "master" if node_id in (None, 0) else str(node_id)


def apply_node_names(nodes: list[dict], names: dict[str, str]) -> list[dict]:
    """Swap Marzban's node names for the ones set in the panel. Nodes given
    the same name are shown as one (e.g. two servers in one country)."""
    merged: dict[str, dict] = {}
    for node in nodes:
        name = names.get(node_key(node["id"])) or node["name"]
        if name in merged:
            merged[name]["used"] += node["used"]
        else:
            merged[name] = {**node, "name": name}
    return sorted(merged.values(), key=lambda n: n["used"], reverse=True)


async def admin_node_usage(api_service, admin: Admins, period: str) -> list[dict]:
    """Which nodes this admin's users used most in the period, biggest first.
    Served from a short cache; a failure raises."""
    key = (admin.id, period)
    cached = _node_cache.get(key)
    if cached and time.time() - cached[0] < _NODE_CACHE_TTL:
        return cached[1]

    end = datetime.utcnow()
    start = end - NODE_PERIODS[period]
    fmt = "%Y-%m-%dT%H:%M:%S"
    owner = admin.username.strip()

    def read() -> list[dict]:
        # Blocking requests underneath, so off the event loop like the sync.
        return asyncio.run(api_service.get_users_usage(start.strftime(fmt), end.strftime(fmt), [owner]))

    usages = await asyncio.to_thread(read)
    nodes = []
    for entry in usages:
        used = int(entry.get("uplink") or 0) + int(entry.get("downlink") or 0)
        if used <= 0:
            continue
        nodes.append({"id": entry.get("node_id"), "name": entry.get("node_name") or "Master", "used": used})
    nodes.sort(key=lambda n: n["used"], reverse=True)
    _node_cache[key] = (time.time(), nodes)
    if len(_node_cache) > 500:
        _node_cache.clear()
    return nodes
