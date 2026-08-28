"""Aggregates the Marzban figures the dashboard shows into one payload.

Kept out of the router so the caching and the window arithmetic stay testable
and the endpoint itself is only wiring.
"""

import time
from datetime import datetime, timedelta

# Window presets offered by the dashboard's period switch.
PERIODS: dict[str, timedelta] = {
    "7h": timedelta(hours=7),
    "1d": timedelta(days=1),
    "3d": timedelta(days=3),
    "1w": timedelta(weeks=1),
    "1m": timedelta(days=30),
    "3m": timedelta(days=90),
}

# Counting online users means pulling the whole user list, which is far too
# heavy to repeat on every dashboard poll, so it is cached briefly.
_ONLINE_CACHE_TTL = 45
_online_cache: dict[str, tuple[float, int]] = {}


def period_bounds(period: str) -> tuple[str, str]:
    """Naive ISO timestamps for the requested window, as Marzban expects."""
    delta = PERIODS.get(period, PERIODS["1d"])
    end = datetime.utcnow()
    start = end - delta
    return start.strftime("%Y-%m-%dT%H:%M:%S"), end.strftime("%Y-%m-%dT%H:%M:%S")


async def _online_count(api_service, panel_name: str) -> int:
    cached = _online_cache.get(panel_name)
    now = time.time()
    if cached and now - cached[0] < _ONLINE_CACHE_TTL:
        return cached[1]

    count = await api_service.count_online_users()
    _online_cache[panel_name] = (now, count)
    return count


async def build_marzban_overview(api_service, panel_name: str, period: str) -> dict:
    stats = await api_service.get_system_stats()

    start, end = period_bounds(period)
    usages = await api_service.get_nodes_usage(start, end)

    nodes = []
    for entry in usages:
        used = int(entry.get("uplink") or 0) + int(entry.get("downlink") or 0)
        if used <= 0:
            # Nodes idle for the whole window would only clutter the chart.
            continue
        nodes.append(
            {
                "id": entry.get("node_id"),
                "name": entry.get("node_name") or "Master",
                "usage": used,
            }
        )
    nodes.sort(key=lambda n: n["usage"], reverse=True)

    incoming = int(stats.get("incoming_bandwidth") or 0)
    outgoing = int(stats.get("outgoing_bandwidth") or 0)

    try:
        online = await _online_count(api_service, panel_name)
    except Exception:
        # The headline figures are worth showing even if the user scan fails.
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
