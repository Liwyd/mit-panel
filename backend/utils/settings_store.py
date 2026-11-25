"""File-based panel settings stored in the persisted data volume.

Keeps runtime-configurable options (login branding + Telegram backup) in a
small JSON file next to the database, so no DB migration is required.
"""

import os
import json
import threading
import time
from datetime import datetime, timedelta, timezone

TEHRAN = timezone(timedelta(hours=3, minutes=30))

DATA_DIR = os.environ.get("MITPANEL_DATA_DIR", "/app/data")
SETTINGS_PATH = os.path.join(DATA_DIR, "settings.json")
LOGO_PATH = os.path.join(DATA_DIR, "logo")

_lock = threading.Lock()

# In-memory cache to avoid reading settings.json from disk on every call.
_settings_cache: dict | None = None
_settings_cache_time: float = 0
_SETTINGS_CACHE_TTL = 10  # seconds

DEFAULTS = {
    "bot_maintenance_eur": "1.00",
    "login_title": "MIT Panel",
    "telegram_bot_token": "",
    "telegram_chat_id": "",
    "backup_enabled": False,
    "backup_interval_hours": 6,
    "bot_enabled": False,
    "bot_token": "",
    "bot_superadmin_ids": "",
    "bot_media_dir": "data/bot_media",
    "bot_min_gb": 200.0,
    "bot_max_gb": 10000.0,
    # Copy overrides for the built-in top-up bot.  They are applied directly to
    # backend.bot.texts at startup and after a dashboard save; keeping them in
    # the panel settings store avoids a second, disconnected configuration file.
    "topup_text_overrides": {},
    # The Mit panel the reseller bots call over its API. This has to be an
    # address the bot *servers* can reach directly: wunli.draking.ir sits
    # behind a tunnel meant for end users in Iran, and the tunnel drops the
    # bot's TLS handshakes, so config creation fails with a context deadline.
    # dwunli.draking.ir points straight at the main server instead.
    "bot_panel_link_url": "https://dwunli.draking.ir:4000/panpan/",
    # Tehran hour the nightly digest goes out (0-23).
    "bot_panel_login_vpn_url": "https://dwunli.draking.ir:4000/panpan/",
    "bot_panel_login_direct_url": "https://wunli.draking.ir:4000/panpan/",
    "bot_digest_hour": 22,
    # Where monitoring agents send their heartbeats, used in the install
    # command. Empty means "whichever domain the panel is open on", which is
    # wrong when one of the panel's domains is routable from the monitored
    # servers and another isn't.
    "agent_base_url": "",
    # The mit-seller server the panel installs new bots on. It is localhost
    # when mit-seller runs on this same server; otherwise its address.
    "mitseller_server": "localhost",
    # The bearer token of that server's provisioning API
    # (install.sh provisioner-setup prints both of these).
    "mitseller_provision_token": "",
    # The self-signed certificate that server presents. The panel trusts this
    # one certificate and nothing else — it is what makes a bare address safe.
    "mitseller_server_cert": "",
    # The address every bot's TLS certificate is issued to. One address for
    # every bot on purpose: it is what the certificate reminder and the
    # renewal notices are sent to, wherever the panel runs.
    "mitseller_cert_email": "mitgetcert@gmail.com",
    # Names admins see for Marzban nodes on their Analytics page, in place of
    # the names set in Marzban: {panel id: {node key: name}}, where the node
    # key is Marzban's node id, or "master" for the main server.
    "node_names": {},
    # Temporary Black Friday theme: dark login page, dark panel and a
    # countdown on the dashboard. It switches itself off once ends_at passes,
    # so nobody has to remember to turn it off. ends_at is ISO 8601 with an
    # offset.
    "black_friday_enabled": False,
    "black_friday_ends_at": "2026-11-29T23:59:59+03:30",
    # What one GB of traffic costs the business, in toman. The profit report
    # subtracts it from the revenue of every GB sold or given away.
    "cost_per_gb": 1000,
    # Traffic multiplier on the panels: when it is 1.4, 1 MB a user really
    # uses takes 1.4 MB of their credit. One GB of credit sold therefore costs
    # only 1 / 1.4 GB of real traffic, so the profit report divides cost_per_gb
    # by it. 1 means no multiplier.
    "traffic_multiplier": 1,
    # Fixed costs of running the business per month (servers, infrastructure,
    # staff), in toman. The profit page subtracts it from gross profit to get
    # net profit.
    "fixed_monthly_cost": 0,
    # Revenue the owner wants each month, in toman. 0 means no target.
    "monthly_revenue_target": 0,
}


def _read() -> dict:
    global _settings_cache, _settings_cache_time
    now = time.time()
    if _settings_cache is not None and now - _settings_cache_time < _SETTINGS_CACHE_TTL:
        return dict(_settings_cache)

    data = dict(DEFAULTS)
    try:
        if os.path.exists(SETTINGS_PATH):
            with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                stored = json.load(f) or {}
            for key in DEFAULTS:
                if key in stored:
                    data[key] = stored[key]
    except Exception:
        pass
    _settings_cache = dict(data)
    _settings_cache_time = now
    return data


def get_settings() -> dict:
    data = _read()
    data["has_logo"] = os.path.exists(LOGO_PATH)
    return data


def update_settings(patch: dict) -> dict:
    global _settings_cache, _settings_cache_time
    with _lock:
        data = _read()
        for key in DEFAULTS:
            if key in patch and patch[key] is not None:
                data[key] = patch[key]
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = SETTINGS_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, SETTINGS_PATH)
        # Invalidate cache so next read picks up the new file
        _settings_cache = None
        _settings_cache_time = 0
    return get_settings()


def parse_black_friday_end(value) -> datetime | None:
    """The theme's end as an aware datetime, or None when it is unusable.
    A value without an offset is read as Tehran time, the panel's zone."""
    if not isinstance(value, str) or not value.strip():
        return None
    try:
        end = datetime.fromisoformat(value.strip())
    except ValueError:
        return None
    if end.tzinfo is None:
        end = end.replace(tzinfo=TEHRAN)
    return end


def black_friday_state(data: dict | None = None) -> dict:
    data = data if data is not None else _read()
    end = parse_black_friday_end(data.get("black_friday_ends_at"))
    active = bool(data.get("black_friday_enabled")) and end is not None and (
        end > datetime.now(timezone.utc)
    )
    return {
        "active": active,
        "ends_at": end.isoformat() if end else None,
    }


def get_public_branding() -> dict:
    data = _read()
    return {
        "login_title": data.get("login_title") or "MIT Panel",
        "has_logo": os.path.exists(LOGO_PATH),
        "black_friday": black_friday_state(data),
    }


def get_node_names() -> dict[str, dict[str, str]]:
    names = _read().get("node_names")
    return dict(names) if isinstance(names, dict) else {}


def set_panel_node_names(panel_id: int, names: dict[str, str]) -> dict[str, str]:
    """Replace one panel's node names. Blank names are dropped, which puts
    the node's Marzban name back."""
    cleaned = {
        str(key): str(name).strip()[:64]
        for key, name in names.items()
        if isinstance(name, str) and name.strip()
    }
    all_names = get_node_names()
    all_names[str(panel_id)] = cleaned
    if not cleaned:
        all_names.pop(str(panel_id), None)
    update_settings({"node_names": all_names})
    return cleaned


def save_logo(content: bytes) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    with open(LOGO_PATH, "wb") as f:
        f.write(content)


def get_logo_path():
    return LOGO_PATH if os.path.exists(LOGO_PATH) else None


def logo_media_type() -> str:
    path = get_logo_path()
    if not path:
        return "application/octet-stream"
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except Exception:
        return "image/png"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if head.startswith(b"GIF8"):
        return "image/gif"
    if head[:4] == b"RIFF" and b"WEBP" in head:
        return "image/webp"
    if head.startswith(b"<svg") or head.startswith(b"<?xml"):
        return "image/svg+xml"
    return "image/png"
