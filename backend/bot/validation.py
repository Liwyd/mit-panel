"""Checks shared by every place the bot accepts a Marzban panel username."""

from __future__ import annotations


def has_space(value: str) -> bool:
    """True when the value carries any whitespace character.

    Telegram lets people paste names containing regular spaces, tabs or
    invisible Unicode spaces. The username is an identifier on the panel and
    inside subscription URLs, so whitespace must never reach Marzban.
    """
    return any(ch.isspace() for ch in value)
