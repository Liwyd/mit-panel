"""Aggregates the Marzban figures the dashboard shows into one payload.

Kept out of the router so the caching and the window arithmetic stay testable
and the endpoint itself is only wiring.
"""

import asyncio
import time
from datetime import datetime, timedelta

from backend.utils.logger import logger


async def _node_statuses(api_service) -> dict:
    """id -> Marzban's status string. Failures degrade to an empty map so a
    status hiccup never blanks the traffic chart that already works."""
    try:
        statuses = await api_service.get_nodes_status()
    except Exception as exc:
        logger.warning(f"Failed to fetch node statuses: {exc}")
        return {}
    return {n["id"]: (n.get("status") or "unknown") for n in statuses if n.get("id") is not None}

# Window presets offered by the dashboard's period switch.
PERIODS: dict[str, timedelta] = {
    "1h": timedelta(hours=1),
    "7h": timedelta(hours=7),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
}

# Counting online users is the one expensive call here, so the request path
# never waits on it: a stale value is served straight away and a refresh runs
# in the background. That keeps the endpoint fast enough that nginx never times
# the panel out, at the cost of the figure lagging by up to one refresh.
_ONLINE_CACHE_TTL = 45
_online_cache: dict[str, tuple[float, int]] = {}
_online_refreshing: set[str] = set()
_background_tasks: set = set()


def period_bounds(period: str) -> tuple[str, str]:
    """Naive ISO timestamps for the requested window, as Marzban expects."""
    delta = PERIODS.get(period, PERIODS["1d"])
    end = datetime.utcnow()
    start = end - delta
    return start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S")


async def _refresh_online(api_service, panel_name: str) -> None:
    """Runs detached. The scan uses blocking requests, so it goes to a worker
    thread to keep the event loop free on a single-core box."""

    def scan() -> int:
        return asyncio.run(api_service.count_online_users())

    try:
        count = await asyncio.to_thread(scan)
        _online_cache[panel_name] = (time.time(), count)
    except Exception as exc:
        logger.warning(f"Online-user scan failed for {panel_name}: {exc}")
    finally:
        _online_refreshing.discard(panel_name)


async def _online_count(api_service, panel_name: str, force: bool = False):
    """Returns the cached count, kicking off a refresh when it is stale.

    None only on the very first call for a panel, before any scan has finished;
    after that a previous value is always served rather than blocking.
    """
    cached = _online_cache.get(panel_name)
    now = time.time()
    fresh = cached and now - cached[0] < _ONLINE_CACHE_TTL

    if fresh and not force:
        return cached[1]

    if panel_name not in _online_refreshing:
        _online_refreshing.add(panel_name)
        task = asyncio.create_task(_refresh_online(api_service, panel_name))
        _background_tasks.add(task)
        task.add_done_callback(_background_tasks.discard)

    return cached[1] if cached else None


async def build_marzban_overview(
    api_service, panel_name: str, period: str, force: bool = False
) -> dict:
    stats = await api_service.get_system_stats()

    start, end = period_bounds(period)
    usages, statuses = await asyncio.gather(
        api_service.get_nodes_usage(start, end),
        _node_statuses(api_service),
    )

    nodes = []
    for entry in usages:
        used = int(entry.get("uplink") or 0) + int(entry.get("downlink") or 0)
        if used <= 0:
            continue
        node_id = entry.get("node_id")
        status = "connected" if node_id is None else statuses.get(node_id, "unknown")
        nodes.append(
            {
                "id": node_id,
                "name": entry.get("node_name") or "Master",
                "usage": used,
                "status": status,
            }
        )
    nodes.sort(key=lambda n: n["usage"], reverse=True)

    incoming = int(stats.get("incoming_bandwidth") or 0)
    outgoing = int(stats.get("outgoing_bandwidth") or 0)

    try:
        online = await _online_count(api_service, panel_name, force=force)
    except Exception:
        online = None

    return {
        "panel": panel_name,
        "period": period,
        "version": stats.get("version"),
        "users": {
            "active": int(stats.get("users_active") or 0),
            "total": int(stats.get("total_user") or 0),
            "online": online,
        },
        "traffic": {
            "incoming": incoming,
            "outgoing": outgoing,
            "total": incoming + outgoing,
        },
        "memory": {
            "used": int(stats.get("mem_used") or 0),
            "total": int(stats.get("mem_total") or 0),
        },
        "cpu": {
            "usage": float(stats.get("cpu_usage") or 0.0),
            "cores": int(stats.get("cpu_cores") or 0),
        },
        "nodes": {
            "total": sum(n["usage"] for n in nodes),
            "items": nodes,
        },
    }
