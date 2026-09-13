"""Bot configuration — reads from the panel's settings.json with env var fallbacks."""

from __future__ import annotations

import os
from pathlib import Path

from backend.config import config as _panel_config
from backend.utils.settings_store import get_settings


class _BotConfig:
    """Thin wrapper around the panel's config, exposing bot-specific fields.
    
    Reads from settings.json first (dashboard-configurable), falls back to
    env vars (.env) for values not yet set via the dashboard.
    """

    @property
    def bot_token(self) -> str:
        s = get_settings()
        return s.get("bot_token") or _panel_config.BOT_TOKEN

    @property
    def superadmin_ids(self) -> str:
        s = get_settings()
        return s.get("bot_superadmin_ids") or _panel_config.BOT_SUPERADMIN_IDS

    @property
    def superadmin_id_list(self) -> list[int]:
        return [
            int(x)
            for x in self.superadmin_ids.split(",")
            if x.strip().lstrip("-").isdigit()
        ]

    @property
    def nexra_panel_api_url(self) -> str:
        return ""

    @property
    def nexra_panel_bot_api_key(self) -> str:
        return ""

    @property
    def sqlite_path(self) -> str:
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "mitpanel.db"
        return str(db_path)

    @property
    def media_dir(self) -> str:
        s = get_settings()
        return s.get("bot_media_dir") or _panel_config.BOT_MEDIA_DIR

    @property
    def min_gb(self) -> float:
        s = get_settings()
        val = s.get("bot_min_gb")
        return float(val) if val is not None else _panel_config.BOT_MIN_GB

    @property
    def max_gb(self) -> float:
        s = get_settings()
        val = s.get("bot_max_gb")
        return float(val) if val is not None else _panel_config.BOT_MAX_GB

    @property
    def warning_scan_interval_seconds(self) -> int:
        return _panel_config.BOT_WARNING_SCAN_INTERVAL

    @property
    def backup_hour(self) -> int:
        return _panel_config.BOT_BACKUP_HOUR


bot_config = _BotConfig()
