"""Checks shared by every place the bot accepts a Marzban panel username."""

from __future__ import annotations


def has_space(value: str) -> bool:
    """True when the value carries any whitespace character.

    Telegram lets people paste names containing regular spaces, tabs or
    invisible Unicode spaces. The username is an identifier on the panel and
    inside subscription URLs, so whitespace must never reach Marzban.
    """
    return any(ch.isspace() for ch in value)


def is_strong_password(password: str) -> bool:
    """At least 8 characters with a letter and a digit — the rule for a password
    a customer picks for a panel they are buying."""
    if len(password) < 8:
        return False
    has_letter = any(c.isalpha() for c in password)
    has_digit = any(c.isdigit() for c in password)
    return has_letter and has_digit
