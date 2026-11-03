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
BUTTON_CONFIG_KEY = "topup_button_config"

BUTTON_ACTIONS = {
    "main": ("topup", "my_panels", "wallet", "change_password", "tutorials", "forecast", "my_invoices", "create_panel", "request_bot", "request_referral", "panel_preview", "support"),
    "unlinked": ("wallet", "my_invoices", "my_panels", "request_referral", "panel_preview", "support"),
    "prospect": ("request_panel", "my_panels", "request_referral", "panel_preview", "support"),
    "superadmin": ("pending_requests", "pending_referrals", "sec_panels", "sec_finance", "sec_users", "tutorials", "sec_settings"),
}

BUTTON_TEXTS = {
    "topup": "BTN_TOPUP", "my_panels": "BTN_MY_PANELS", "wallet": "BTN_WALLET",
    "change_password": "BTN_CHANGE_PASSWORD", "tutorials": "BTN_TUTORIALS", "forecast": "BTN_FORECAST",
    "my_invoices": "BTN_MY_INVOICES", "create_panel": "BTN_CREATE_PANEL", "request_bot": "BTN_REQUEST_BOT",
    "request_referral": "BTN_REQUEST_REFERRAL", "panel_preview": "BTN_PANEL_PREVIEW", "support": "BTN_SUPPORT",
    "request_panel": "BTN_REQUEST_PANEL", "pending_requests": "BTN_PENDING_REQUESTS",
    "pending_referrals": "BTN_PENDING_REFERRAL_REQUESTS", "sec_panels": "BTN_SEC_PANELS",
    "sec_finance": "BTN_SEC_FINANCE", "sec_users": "BTN_SEC_USERS", "sec_settings": "BTN_SEC_SETTINGS",
}

def button_config() -> dict:
    raw = get_settings().get(BUTTON_CONFIG_KEY, {})
    result = {}
    if not isinstance(raw, dict):
        return result
    for menu, actions in BUTTON_ACTIONS.items():
        config = raw.get(menu, {})
        if not isinstance(config, dict):
            continue
        rows = config.get("layout")
        if isinstance(rows, list) and all(isinstance(row, list) for row in rows):
            flat = [key for row in rows for key in row]
            labels = config.get("labels", {})
            buttons = config.get("buttons", {})
            if len(flat) == len(set(flat)) and set(flat) == set(actions) and all(1 <= len(row) <= 3 for row in rows) and isinstance(labels, dict) and isinstance(buttons, dict):
                result[menu] = {"layout": rows, "labels": labels, "buttons": buttons}
    return result


def configured_button_label(menu: str, action: str) -> str:
    default = getattr(texts, BUTTON_TEXTS[action])
    config = button_config().get(menu, {})
    label = config.get("labels", {}).get(action)
    if isinstance(label, str) and label.strip():
        return label.strip()
    return default


def normalize_menu_text(value: str | None) -> str | None:
    if not value:
        return value
    for menu, actions in BUTTON_ACTIONS.items():
        for action in actions:
            if value == configured_button_label(menu, action):
                return getattr(texts, BUTTON_TEXTS[action])
    return value

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
