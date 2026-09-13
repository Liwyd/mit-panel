"""Bot configuration — reads from the panel's .env via the shared Setting class."""

from __future__ import annotations

import os
from pathlib import Path

from backend.config import config as _panel_config


class _BotConfig:
    """Thin wrapper around the panel's config, exposing bot-specific fields."""

    @property
    def bot_token(self) -> str:
        return _panel_config.BOT_TOKEN

    @property
    def superadmin_ids(self) -> str:
        return _panel_config.BOT_SUPERADMIN_IDS

    @property
    def superadmin_id_list(self) -> list[int]:
        return [
            int(x)
            for x in self.superadmin_ids.split(",")
            if x.strip().lstrip("-").isdigit()
        ]

    @property
    def nexra_panel_api_url(self) -> str:
        # Not used in embedded mode — the bot calls panel functions directly.
        # Kept for interface compatibility.
        return ""

    @property
    def nexra_panel_bot_api_key(self) -> str:
        return ""

    @property
    def sqlite_path(self) -> str:
        # Use the panel's own database file — no separate DB.
        db_path = Path(__file__).resolve().parent.parent.parent / "data" / "mitpanel.db"
        return str(db_path)

    @property
    def media_dir(self) -> str:
        return _panel_config.BOT_MEDIA_DIR

    @property
    def min_gb(self) -> float:
        return _panel_config.BOT_MIN_GB

    @property
    def max_gb(self) -> float:
        return _panel_config.BOT_MAX_GB

    @property
    def warning_scan_interval_seconds(self) -> int:
        return _panel_config.BOT_WARNING_SCAN_INTERVAL

    @property
    def backup_hour(self) -> int:
        return _panel_config.BOT_BACKUP_HOUR


bot_config = _BotConfig()
