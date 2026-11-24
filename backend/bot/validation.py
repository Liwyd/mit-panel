"""Checks shared by every place a reseller panel username or password is accepted.

The MIT Panel login form (`frontend/src/types/index.ts` → `USERNAME_REGEX`,
3–50 characters) only lets in usernames made of English letters, digits,
`_`, `.` and `-` that start with a letter or digit. A panel created with any
other name can never be logged into, so the bot, the bot HTTP API and the
superadmin API all use `is_valid_username` — keep it in step with that form.
"""

from __future__ import annotations

import re

USERNAME_MIN_LENGTH = 3
USERNAME_MAX_LENGTH = 50
PASSWORD_MIN_LENGTH = 8
PASSWORD_MAX_LENGTH = 100

# re.ASCII + fullmatch: no Persian/Arabic digits, no look-alike Unicode
# letters, no zero-width characters and no trailing newline slipping past `$`.
_USERNAME_RE = re.compile(
    r"[A-Za-z0-9][A-Za-z0-9_.\-]{%d,%d}"
    % (USERNAME_MIN_LENGTH - 1, USERNAME_MAX_LENGTH - 1),
    re.ASCII,
)


def has_space(value: str) -> bool:
    """True when the value carries any whitespace character.

    Telegram lets people paste names containing regular spaces, tabs or
    invisible Unicode spaces. The username is an identifier on the panel and
    inside subscription URLs, so whitespace must never reach Marzban.
    """
    return any(ch.isspace() for ch in value)


def is_valid_username(value: str) -> bool:
    """True when the MIT Panel login form would accept this username."""
    return isinstance(value, str) and _USERNAME_RE.fullmatch(value) is not None


def _is_ascii_letter(ch: str) -> bool:
    return ("a" <= ch <= "z") or ("A" <= ch <= "Z")


def is_strong_password(password: str) -> bool:
    """The rule for a password a customer picks for a panel they are buying.

    8–100 characters (the login form allows at most 100), printable ASCII only
    — no spaces, control or Persian characters that may not be typed the same
    way on the login page — with at least one English letter and one digit.
    """
    if not isinstance(password, str):
        return False
    if not PASSWORD_MIN_LENGTH <= len(password) <= PASSWORD_MAX_LENGTH:
        return False
    if any(not ("!" <= ch <= "~") for ch in password):
        return False
    has_letter = any(_is_ascii_letter(c) for c in password)
    has_digit = any("0" <= c <= "9" for c in password)
    return has_letter and has_digit
