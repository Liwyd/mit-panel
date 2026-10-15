"""Talking to a mit-seller server: install a bot, and set its panel up.

The panel runs in a container with no shell and no SSH, so the only way it can
get a bot installed is to ask the mit-seller server over the provisioning API
that `install.sh provisioner-setup` starts. The panel holds a bearer token for
it and trusts the self-signed certificate that server presents, and nothing
else; that pairing is what makes a bare address safe to send a BotFather token
to.
"""

from __future__ import annotations

import os

import httpx

from backend.utils.logger import logger
from backend.utils.settings_store import DATA_DIR, get_settings

# Fixed so the panel needs the server's address and not a second setting to
# get wrong. See mit-seller's provisioner.DefaultPort.
PROVISION_PORT = 18100

# install.sh new takes a while — DNS, certbot, nginx, mysql — so the panel
# waits for it rather than reporting a failure that has not happened yet.
TIMEOUT = httpx.Timeout(150.0, connect=10.0)
BOT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# The name every bot's reseller panel is filed under, in Persian, so it reads
# the same in every bot's "مدیریت پنل‌ها".
VIP_PANEL_NAME = "پنل VIP"

_CERT_PATH = os.path.join(DATA_DIR, "mitseller-provision.crt")


class MitSellerError(Exception):
    """Anything the mit-seller server said or did that we could not use."""


def provision_configured() -> bool:
    """Can this panel install a bot? The address defaults to localhost, so an
    unconfigured panel still counts as configured only when a token is set."""
    s = get_settings()
    return bool(s.get("mitseller_server") and s.get("mitseller_provision_token"))


def _provision_cert() -> str | None:
    """Write the trusted certificate out where httpx can be pointed at it."""
    pem = (get_settings().get("mitseller_server_cert") or "").strip()
    if not pem:
        return None
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = _CERT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(pem + "\n")
    os.replace(tmp, _CERT_PATH)
    return _CERT_PATH


async def provision_bot(
    *,
    token: str,
    domain: str,
    admin_id: int,
    n: int | None = None,
    cert_email: str = "",
    mit_secret: str = "",
    panel_url: str = "",
    panel_user: str = "",
    panel_pass: str = "",
) -> dict:
    """Ask the mit-seller server to install a bot and connect it here.

    Returns the provisioner's data: the bot's address, its two API keys, the
    management code and the number it was installed as.
    """
    s = get_settings()
    server = (s.get("mitseller_server") or "").strip()
    bearer = (s.get("mitseller_provision_token") or "").strip()
    if not server or not bearer:
        raise MitSellerError("سرور mit-seller در تنظیمات پنل ثبت نشده است")
    if not token or not domain:
        raise MitSellerError("توکن یا دامنه خالی است")
    if not admin_id:
        raise MitSellerError("آیدی عددی ادمین خالی است")

    cert = _provision_cert()
    verify: bool | str = cert if cert else False
    if cert is None:
        # No certificate pinned yet: refuse rather than send a BotFather token
        # over a connection nobody has vouched for.
        raise MitSellerError(
            "گواهی سرور mit-seller در تنظیمات پنل ثبت نشده است "
            "(install.sh provisioner-print را روی سرور اجرا کنید)"
        )

    body = {
        "token": token,
        "domain": domain,
        "admin_id": str(admin_id),
        "cert_email": cert_email or "",
        "mit_secret": mit_secret or "",
        "panel_url": panel_url or "",
        "panel_user": panel_user or "",
        "panel_pass": panel_pass or "",
    }
    if n:
        body["n"] = str(n)

    url = f"https://{server}:{PROVISION_PORT}/provision"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT, verify=verify) as client:
            res = await client.post(
                url,
                json=body,
                headers={"Authorization": f"Bearer {bearer}"},
            )
    except httpx.HTTPError as exc:
        raise MitSellerError(f"سرور mit-seller در دسترس نیست: {exc.__class__.__name__}") from exc

    try:
        payload = res.json()
    except ValueError as exc:
        raise MitSellerError(f"پاسخ نامعتبر از سرور mit-seller (HTTP {res.status_code})") from exc

    if res.status_code != 200 or not payload.get("ok"):
        raise MitSellerError(payload.get("error") or f"ساخت ربات ناموفق بود (HTTP {res.status_code})")
    return payload.get("data") or {}


async def push_vip_panel(
    *,
    bot_url: str,
    owner_key: str,
    username: str,
    password: str,
    panel_url: str,
) -> str:
    """Put the reseller's panel into the bot's «مدیریت پنل‌ها» as «پنل VIP».

    The bot sells from a panel of its own, so after it is installed nobody
    should have to type the panel in by hand. This writes the one row it needs,
    creating it or updating it — the create endpoint refuses a second panel
    with the same name, so an existing row is updated rather than duplicated.

    `username`/`password` are the reseller's own Marzban login, not the panel's
    sudo account: the bot has to create users as that reseller, and giving every
    reseller bot the sudo password would be a much bigger thing to have leaked.
    """
    if not username or not panel_url:
        raise MitSellerError("نام کاربری یا آدرس پنل خالی است")

    found: dict | None = None
    try:
        async with httpx.AsyncClient(timeout=BOT_TIMEOUT) as client:
            res = await client.get(
                f"{bot_url}/api/v1/panels",
                headers={"Authorization": f"Bearer {owner_key}"},
            )
            if res.status_code == 200:
                for row in (res.json().get("data") or []):
                    if row.get("name_panel") == VIP_PANEL_NAME:
                        found = row
                        break
            if found is not None:
                put = await client.put(
                    f"{bot_url}/api/v1/panels/{found.get('id')}",
                    headers={"Authorization": f"Bearer {owner_key}"},
                    json={
                        "url_panel": panel_url,
                        "username_panel": username,
                        "password_panel": password or "",
                    },
                )
                if put.status_code != 200:
                    raise MitSellerError(put.json().get("error") or f"HTTP {put.status_code}")
                return f"پنل «{VIP_PANEL_NAME}» به‌روزرسانی شد"
            post = await client.post(
                f"{bot_url}/api/v1/panels",
                headers={"Authorization": f"Bearer {owner_key}"},
                json={
                    "name": VIP_PANEL_NAME,
                    "type": "marzban",
                    "url": panel_url,
                    "username": username,
                    "password": password or "",
                },
            )
            if post.status_code != 200:
                raise MitSellerError(post.json().get("error") or f"HTTP {post.status_code}")
            return f"پنل «{VIP_PANEL_NAME}» ساخته شد"
    except httpx.HTTPError as exc:
        raise MitSellerError(f"ربات در دسترس نیست: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise MitSellerError("پاسخ نامعتبر از ربات") from exc


async def set_bot_admin(*, bot_url: str, owner_key: str, admin_telegram_id: int) -> None:
    """Make the bot's Telegram admin the reseller this panel just created."""
    if not admin_telegram_id:
        return
    try:
        async with httpx.AsyncClient(timeout=BOT_TIMEOUT) as client:
            res = await client.put(
                f"{bot_url}/api/v1/settings",
                headers={"Authorization": f"Bearer {owner_key}"},
                json={"admin_id": admin_telegram_id},
            )
        if res.status_code != 200:
            logger.warning(
                f"could not set the bot's admin to {admin_telegram_id}: HTTP {res.status_code}"
            )
    except (httpx.HTTPError, ValueError) as exc:
        logger.warning(f"could not set the bot's admin: {exc!r}")
