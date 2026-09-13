"""Helpers for working with a person's panels.

One Telegram account can own several reseller panels, so any flow that acts on
"their panel" has to establish *which* one first. When they own exactly one the
question is skipped entirely — only genuinely ambiguous cases show a picker.
"""

from __future__ import annotations

from aiogram.types import Message

import logging

from backend.bot import keyboards, texts
from backend.bot import db
from backend.bot import panel_client as nexra_panel
from backend.bot.units import bytes_to_gb

logger = logging.getLogger(__name__)


async def safe_get_admins(message: Message) -> list[dict] | None:
    """Their panels, or None if the panel API couldn't be reached.

    None is distinct from []: an empty list means "no panels linked", None means
    "we don't know". The caller must not treat an outage as an unlinked account,
    and the user is told what happened rather than being met with silence.
    """
    try:
        admins = await nexra_panel.get_admins(message.from_user.id)
    except Exception as exc:
        logger.error(f"panel lookup failed for {message.from_user.id}: {exc}")
        await message.answer(texts.PANEL_UNREACHABLE)
        return None
    if admins:
        db.set_user_linked(message.from_user.id, True)
    return admins


def format_expiry(expiry) -> str:
    if not expiry:
        return texts.PANEL_NO_EXPIRY
    return texts.PANEL_EXPIRY_LINE.format(expiry=str(expiry)[:10])


def format_panel_line(admin: dict) -> str:
    return texts.PANEL_LINE.format(
        username=admin["username"],
        remaining_gb=bytes_to_gb(admin.get("traffic")),
        initial_gb=bytes_to_gb(admin.get("initial_traffic")),
        expiry_line=format_expiry(admin.get("expiry_date")),
    )


async def owned_panel(telegram_id: int, username: str) -> dict | None:
    """Fetch one panel only if this Telegram account actually owns it — callback
    data is user-supplied, so it can't be trusted to name their own panel."""
    admins = await nexra_panel.get_admins(telegram_id)
    return next((a for a in admins if a["username"] == username), None)


async def choose_panel(message: Message, action: str) -> dict | None:
    """Return their panel when unambiguous; otherwise show a picker and return None.

    `action` is embedded in the picker's callback data so the tap comes back to
    the right flow (e.g. "topup" vs "pwd").
    """
    admins = await safe_get_admins(message)
    if admins is None:
        return None
    if not admins:
        await message.answer(texts.NOT_LINKED_RETRY)
        return None
    if len(admins) == 1:
        return admins[0]
    await message.answer(
        texts.CHOOSE_PANEL, reply_markup=keyboards.panel_picker_kb(admins, action)
    )
    return None
