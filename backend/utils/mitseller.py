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
import ssl

import httpx

from backend.utils.logger import logger
from backend.utils.settings_store import DATA_DIR, get_settings

# Fixed so the panel needs the server's address and not a second setting to
# get wrong. See mit-seller's provisioner.DefaultPort.
PROVISION_PORT = 18100

# install.sh new takes a while — DNS, certbot, nginx, mysql — so the panel
# waits for it rather than reporting a failure that has not happened yet. The
# server keeps going for 15 minutes (its WriteTimeout), and giving up before
# it finishes tells the superadmin the install failed while the bot is still
# being built — the retry then asks for a second bot on the same domain.
# Wait most of that window, but not all of it, so a dead server still returns.
TIMEOUT = httpx.Timeout(600.0, connect=10.0)
BOT_TIMEOUT = httpx.Timeout(30.0, connect=10.0)

# The name every bot's reseller panel is filed under, in Persian, so it reads
# the same in every bot's "مدیریت پنل‌ها".
VIP_PANEL_NAME = "پنل VIP"
MIT_PANEL_NAME = "پنل MIT"

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


def _pinned_context(pem_path: str) -> ssl.SSLContext:
    """Trust this one certificate, whatever it is called.

    This is pinning, not host verification: the peer is accepted because it
    presents the certificate we were handed, not because its name matches the
    address. That is the whole point of the pairing — the panel writes to the
    address as it was configured, and the server was given a self-signed
    certificate with no name that address would have.
    """
    ctx = ssl.create_default_context()
    try:
        ctx.load_verify_locations(pem_path)
    except (OSError, ssl.SSLError) as exc:
        raise MitSellerError(
            "گواهی سرور mit-seller در تنظیمات پنل معتبر نیست "
            "(install.sh provisioner-print را دوباره روی سرور اجرا و گواهی را تازه کن)"
        ) from exc
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_REQUIRED
    return ctx


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
    if cert is None:
        # No certificate pinned yet: refuse rather than send a BotFather token
        # over a connection nobody has vouched for.
        raise MitSellerError(
            "گواهی سرور mit-seller در تنظیمات پنل ثبت نشده است "
            "(install.sh provisioner-print را روی سرور اجرا کنید)"
        )
    verify: ssl.SSLContext | bool = _pinned_context(cert)

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


async def add_bot_admin(*, bot_url: str, owner_key: str, admin_id: int) -> None:
    """Give a second person admin on a bot that is already installed.

    The bot's *main* admin is written into its config when it is built and the
    API refuses to remove them, so everyone else — the admin the bot was built
    for, the buyer behind a request — is added here instead. An ordinary admin
    has every power bar removing that first name, and this one can be given or
    taken away later without touching the server.
    """
    if not admin_id:
        return
    try:
        async with httpx.AsyncClient(timeout=BOT_TIMEOUT) as client:
            res = await client.post(
                f"{bot_url}/api/v1/admins",
                headers={"Authorization": f"Bearer {owner_key}"},
                json={"id": str(admin_id)},
            )
        if res.status_code != 200:
            raise MitSellerError(res.json().get("error") or f"HTTP {res.status_code}")
    except httpx.HTTPError as exc:
        raise MitSellerError(f"ربات در دسترس نیست: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise MitSellerError("پاسخ نامعتبر از ربات") from exc


async def verify_panel_login(panel_base: str, username: str, password: str) -> bool | None:
    """Ask the Mit Panel whether this account can sign in.

    True when the panel says yes, False when it says no, and None when the
    panel could not be reached at all: an unreachable panel is not a wrong
    password, and a working account must not be thrown away over it.
    """
    if not panel_base or not username or not password:
        return None
    try:
        # The panel's own certificate is the one the bot trusts blindly too,
        # so this check says the same thing the bot will find.
        async with httpx.AsyncClient(timeout=httpx.Timeout(10.0, connect=5.0), verify=False) as client:
            res = await client.post(
                f"{panel_base.rstrip('/')}/login",
                data={"username": username, "password": password},
            )
    except httpx.HTTPError:
        return None
    if res.status_code == 200:
        try:
            return bool((res.json() or {}).get("success"))
        except ValueError:
            return None
    if res.status_code in (400, 401, 403, 422):
        return False
    return None


async def push_mit_panel(
    *,
    bot_url: str,
    owner_key: str,
    name: str,
    panel_url: str,
    panel_user: str,
    panel_password: str,
    marzban_url: str,
    marzban_user: str,
    marzban_password: str,
) -> str:
    """Put the reseller's own Mit Panel into the bot's panel list.

    A "mit" panel is two servers in one row: the reseller's Mit Panel, where
    their traffic is counted, and the Marzban behind it, where the accounts
    are made. The bot signs in to the panel as the reseller, so they can sell
    from their own panel without adding anything by hand afterwards.

    The bot's API names these fields differently when a row is created
    (`url`, `username`, `password`) and when it is updated (`url_panel`,
    `username_panel`, `password_panel`), so both shapes are sent.
    """
    headers = {"Authorization": f"Bearer {owner_key}"}
    try:
        async with httpx.AsyncClient(timeout=BOT_TIMEOUT) as client:
            res = await client.get(f"{bot_url}/api/v1/panels", headers=headers)
            found: dict | None = None
            if res.status_code == 200:
                for row in (res.json().get("data") or []):
                    if row.get("name_panel") == name:
                        found = row
                        break
            if found is not None:
                put = await client.put(
                    f"{bot_url}/api/v1/panels/{found.get('id')}",
                    headers=headers,
                    json={
                        "url_panel": panel_url,
                        "username_panel": panel_user,
                        "password_panel": panel_password,
                        "marzban_url_direct": marzban_url,
                        "marzban_username_direct": marzban_user,
                        "marzban_password_direct": marzban_password,
                    },
                )
                if put.status_code != 200:
                    raise MitSellerError(put.json().get("error") or f"HTTP {put.status_code}")
                return f"پنل «{name}» به‌روزرسانی شد"
            post = await client.post(
                f"{bot_url}/api/v1/panels",
                headers=headers,
                json={
                    "name": name,
                    "type": "mit",
                    "url": panel_url,
                    "username": panel_user,
                    "password": panel_password,
                    "marzban_url_direct": marzban_url,
                    "marzban_username_direct": marzban_user,
                    "marzban_password_direct": marzban_password,
                },
            )
            if post.status_code != 200:
                raise MitSellerError(post.json().get("error") or f"HTTP {post.status_code}")
            return f"پنل «{name}» ساخته شد"
    except httpx.HTTPError as exc:
        raise MitSellerError(f"ربات در دسترس نیست: {exc.__class__.__name__}") from exc
    except ValueError as exc:
        raise MitSellerError("پاسخ نامعتبر از ربات") from exc
