"""Reads each Marzban panel's users to record what an admin's users consumed.

This is what fills `admin_usage_hourly` for the Analytics page. It is
deliberately **read-only**: it never charges, refunds or edits anything, so a
bug in here can only cost chart accuracy — never a reseller's balance. The
balance paths are and stay `backend/services/limit_handler.py` (charges made
through the panel) and `backend/bot/usage_sync.py` (the twice-daily sweep that
charges users made outside it).

`backend/services/marzban/sync.py` also reads users, but it charges as it goes
and mit deliberately never runs it as a background loop, so usage cannot be
recorded from there. This loop walks the same users on its own, sums
`used_traffic` per owner, and books the growth since its own last reading into
the hour it was seen. The first reading per admin is a baseline, not traffic:
whatever had already been consumed must not appear as a day's usage.

The same first reading is also when an admin's sales are backfilled from the
users' own creation dates (once), so the sales average has a full window on
day one instead of starting empty.

Every panel is read sequentially with a pause in between — the rule the usage
sync sweeps by — so no instant of a pass has more than one panel's worth of
work in flight.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta

from backend.db import crud, engin
from backend.db.model import AdminTrafficLog
from backend.services.marzban.sync import _created_at
from backend.utils import analytics
from backend.utils.logger import logger

# Seconds between readings of the panels.
RECORD_INTERVAL = 300
PAGE_SIZE = 500
# Pacing inside one panel's user list, so a very large panel is read over a
# few seconds instead of back-to-back calls (same values the usage sync uses).
PAGE_DELAY = 0.25
BETWEEN_PANELS = 1.0
# How often the 90-day retention prune runs, counted in passes.
PRUNE_EVERY = 12

# admin_id -> total used_traffic last seen, in memory only. A restart simply
# rebaselines instead of recording the whole gap as one hour of usage.
_totals: dict[int, int] = {}


def _slim(user: dict) -> dict | None:
    """The four fields the recording needs; None for a user we can't attribute.

    Full user records are large (every inbound's links included), so the
    reduction happens here, in the worker thread, before the raw list is
    dropped — the memory rule the usage sync sweeps by.
    """
    owner = str(((user.get("admin") or {}).get("username")) or "")
    if not owner:
        return None  # Belongs to the panel itself: nobody's to record.
    try:
        used = int(user.get("used_traffic") or 0)
        limit = int(user.get("data_limit") or 0)
    except (TypeError, ValueError):
        return None
    return {
        "owner": owner,
        "used": max(used, 0),
        "limit": max(limit, 0),
        "created": _created_at(user),
    }


async def _read_panel(panel) -> list[dict]:
    """One panel's users, slimmed, with the blocking read off the event loop.

    The HTTP calls and the JSON parsing are synchronous, so they run in a
    worker thread with their own event loop — the same rule the sync and the
    usage sweep follow. `get_all_users_paginated` raises rather than returning
    a partial list, and a partial list would book the shortfall as traffic the
    users had stopped using.
    """

    def read() -> list[dict]:
        from backend.services.marzban.api import APIService

        api = APIService(url=panel.url, username=panel.username, password=panel.password)
        raw = asyncio.run(
            api.get_all_users_paginated(page_size=PAGE_SIZE, page_delay=PAGE_DELAY)
        )
        slim = []
        for user in raw:
            entry = _slim(user)
            if entry is not None:
                slim.append(entry)
        return slim

    return await asyncio.to_thread(read)


def _backfill_sales(db, admin_id: int, admin_username: str, rows: list[dict], read_at: datetime) -> None:
    """Log the sales that happened before this log existed, once.

    Read from the users' own creation dates: the first reading of an admin's
    users already has them, so this costs no extra panel request. A 0-sized
    marker row marks it as done, so a restart never runs it again. Runs on the
    caller's session, so it commits (or is rolled back) with the usage it
    belongs to — two sessions writing SQLite at once would only deadlock.
    """
    if analytics.sales_backfilled(db, admin_id):
        return
    started = analytics.sales_log_start(db, admin_id)
    until = min(started, read_at) if started else read_at
    since = until - timedelta(days=analytics.DAYS_SHOWN)
    count = 0
    for row in rows:
        created = row["created"]
        if created and since <= created < until and row["limit"] > 0:
            db.add(
                AdminTrafficLog(
                    admin_id=admin_id,
                    amount=row["limit"],
                    kind="backfill",
                    created_at=created,
                )
            )
            count += 1
    db.add(AdminTrafficLog(admin_id=admin_id, amount=0, kind="backfill", created_at=read_at))
    logger.info(
        f"Analytics: logged {count} earlier sales of {admin_username} from Marzban"
    )


def _record_panel(panel_name: str, rows: list[dict], now: datetime) -> None:
    """Book each owner's growth since the last pass into their usage hour.

    Two phases: resolving admins is read-only, then every write for the panel
    goes through one session and one commit. The baselines only move once that
    commit lands, so a failed pass is retried with its deltas intact instead
    of quietly leaving a hole in the chart.
    """
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["owner"], []).append(row)

    plan: list[tuple[int, str, list[dict]]] = []
    db = engin.sessionLocal()
    try:
        for owner, owned in grouped.items():
            admin = crud.get_admin_by_username(db, owner)
            # Same guard the billing sync uses: a name that belongs to another
            # panel's admin is nobody's usage here.
            if admin is None or admin.panel != panel_name:
                continue
            # Plain values, not the instance: this session is closed below and
            # the writes happen on a different one, where reading a detached
            # object would raise.
            plan.append((admin.id, admin.username, owned))
    finally:
        db.close()

    if not plan:
        return

    db = engin.sessionLocal()
    try:
        seen: dict[int, int] = {}
        for admin_id, admin_username, owned in plan:
            total = sum(r["used"] for r in owned)
            before = _totals.get(admin_id)
            if before is None:
                # First sighting: a baseline, not traffic — whatever had been
                # used before this reading must not appear as a day's usage.
                # It is also the moment the sales log can be backfilled.
                _backfill_sales(db, admin_id, admin_username, owned, now)
            else:
                delta = total - before
                # A fall means a user was deleted or its usage reset; the
                # baseline comes down with it, so nothing is booked.
                if delta > 0:
                    analytics.record_usage(db, admin_id, delta, now)
            seen[admin_id] = total
        db.commit()
        _totals.update(seen)
    except Exception as exc:
        db.rollback()
        # Read-only loop: only the chart loses this pass, never a balance.
        logger.warning(f"Analytics: could not record usage of {panel_name}: {exc}")
    finally:
        db.close()


def _prune() -> None:
    """Drop analytics rows past the retention window."""
    db = engin.sessionLocal()
    try:
        analytics.prune(db)
    except Exception as exc:
        db.rollback()
        logger.warning(f"Analytics: prune failed: {exc}")
    finally:
        db.close()


async def _pass() -> None:
    db = engin.sessionLocal()
    try:
        panels = [
            p
            for p in crud.get_all_panels(db)
            if p.panel_type == "marzban" and p.is_active
        ]
    finally:
        db.close()

    now = datetime.utcnow()
    for panel in panels:
        try:
            rows = await _read_panel(panel)
            _record_panel(panel.name, rows, now)
        except Exception as exc:
            # One unreachable panel must not stop the others being read.
            logger.warning(f"Usage recorder: could not read panel {panel.name}: {exc}")
        await asyncio.sleep(BETWEEN_PANELS)


async def run_usage_recorder() -> None:
    """The loop's entry point: pass, wait, pass again. Never raises out."""
    # Let the app finish starting before the first (and largest) read.
    await asyncio.sleep(15)
    passes = 0
    while True:
        try:
            await _pass()
            passes += 1
            if passes % PRUNE_EVERY == 0:
                await asyncio.to_thread(_prune)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.error(f"Usage recorder pass failed: {exc}")
        await asyncio.sleep(RECORD_INTERVAL)
