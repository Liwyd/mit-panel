"""Dashboard-managed copy for the built-in top-up bot.

The bot imports :mod:`backend.bot.texts` everywhere, so overrides are applied
to that module rather than maintained in a parallel configuration file that
the running bot would never consult.  Keeping the immutable defaults here also
makes a reset deterministic.
"""

from __future__ import annotations

from string import Formatter

from backend.bot import texts
from backend.utils.settings_store import get_settings


TEXT_OVERRIDES_KEY = "topup_text_overrides"

# Only strings are copy.  Button labels are deliberately excluded: aiogram
# evaluates the matching reply-keyboard filters while routers are registered,
# so changing one live would render that button inert until a restart.  The
# dashboard must never offer a control it cannot apply safely.
DEFAULT_TEXTS = {
    name: value
    for name, value in vars(texts).items()
    if name.isupper() and isinstance(value, str) and not name.startswith("BTN_")
}


def fields(value: str) -> list[str]:
    """Return unique ``str.format`` field names in their display order."""
    seen: set[str] = set()
    result: list[str] = []
    for _, field_name, _, _ in Formatter().parse(value):
        if field_name and field_name not in seen:
            seen.add(field_name)
            result.append(field_name)
    return result


def configured_overrides() -> dict[str, str]:
    raw = get_settings().get(TEXT_OVERRIDES_KEY, {})
    if not isinstance(raw, dict):
        return {}
    return {
        name: value
        for name, value in raw.items()
        if name in DEFAULT_TEXTS and isinstance(value, str) and fields(value) == fields(DEFAULT_TEXTS[name])
    }


def apply_text_overrides() -> None:
    """Reset copy to defaults, then apply the validated persisted overrides."""
    for name, value in DEFAULT_TEXTS.items():
        setattr(texts, name, value)
    for name, value in configured_overrides().items():
        setattr(texts, name, value)
