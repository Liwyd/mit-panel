"""Derives a server's connection status from its last heartbeat.

Not stored on the row itself - the agent pushes every ~10s, so "connected"
is just "we heard from it recently" computed on read.
"""

from datetime import datetime, timedelta

HEARTBEAT_TIMEOUT = timedelta(seconds=25)
CONNECTING_GRACE = timedelta(minutes=5)


def server_status(server) -> str:
    now = datetime.utcnow()

    if server.last_seen_at is not None:
        return "connected" if now - server.last_seen_at <= HEARTBEAT_TIMEOUT else "disconnected"

    if server.created_at is not None and now - server.created_at <= CONNECTING_GRACE:
        return "connecting"

    return "disconnected"
