"""Shared helpers for manual invoices — deadlines and formatting.

Invoices are deliberately independent of panels: they bill for anything done by
hand (a one-off setup, a migration, extra support) for someone who may not even
own a panel.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from backend.bot import texts

TEHRAN = ZoneInfo("Asia/Tehran")

# key -> (button label, offset from now; None means no deadline at all)
DUE_OPTIONS: dict[str, tuple[str, timedelta | None]] = {
    "now": (texts.DUE_IMMEDIATE, timedelta(0)),
    "today": (texts.DUE_TODAY, timedelta(hours=12)),
    "3d": (texts.DUE_3_DAYS, timedelta(days=3)),
    "1w": (texts.DUE_1_WEEK, timedelta(days=7)),
    "none": (texts.DUE_NONE, None),
}


def due_at_for(key: str) -> str | None:
    """Absolute deadline for a chosen option, as an ISO string (None = open-ended)."""
    label_offset = DUE_OPTIONS.get(key)
    if not label_offset:
        return None
    _, offset = label_offset
    if offset is None:
        return None
    return (datetime.now(TEHRAN) + offset).isoformat()


def describe_due(due_at: str | None) -> str:
    """Human-readable deadline, including how overdue it already is."""
    if not due_at:
        return texts.DUE_NONE
    try:
        due = datetime.fromisoformat(due_at).astimezone(TEHRAN)
    except Exception:
        return texts.DUE_NONE

    now = datetime.now(TEHRAN)
    stamp = due.strftime("%Y-%m-%d %H:%M")
    if now >= due:
        days = (now - due).days
        return f"{stamp} (سررسید گذشته — {days} روز)" if days else f"{stamp} (سررسید گذشته)"
    return stamp


def is_due(due_at: str | None) -> bool:
    """Whether this invoice has reached its deadline and should be chased."""
    if not due_at:
        return False
    try:
        return datetime.now(TEHRAN) >= datetime.fromisoformat(due_at).astimezone(TEHRAN)
    except Exception:
        return False
