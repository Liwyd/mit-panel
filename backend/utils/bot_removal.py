"""Deleting a sales bot for good: from its server, then from this panel.

Disconnecting a bot (`crud.remove_bot`) only forgets it here; the bot keeps
running on the mit-seller server with its database, site, certificate and
backups. This asks that server to delete all of it first, and forgets the bot
here only once that worked — a failed removal leaves the row in place, so the
superadmin can still see the bot and try again.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from backend.db import crud, engin
from backend.utils import mitseller
from backend.utils.logger import logger


class BotRemovalError(Exception):
    """The bot could not be removed; the message is shown to the superadmin."""


def bot_domain(url: str) -> str:
    """The hostname a bot is served on, from its stored base address."""
    raw = (url or "").strip()
    if "://" not in raw:
        raw = "https://" + raw
    return (urlsplit(raw).hostname or "").lower()


async def remove_bot_completely(bot_id: int, final_backup: bool = True) -> dict:
    """Delete bot `bot_id` from its server and then from this panel.

    Returns the bot's name and domain. Raises BotRemovalError, with the row
    left untouched, when anything goes wrong.
    """
    with engin.sessionLocal() as session:
        bot = crud.get_bot_by_id(session, bot_id)
        if bot is None:
            raise BotRemovalError("ربات پیدا نشد")
        name, url = bot.name, bot.url
    domain = bot_domain(url)
    if not domain:
        raise BotRemovalError("دامنه این ربات معلوم نیست")
    if not mitseller.provision_configured():
        raise BotRemovalError("سرور mit-seller در تنظیمات پنل ثبت نشده است")

    try:
        await mitseller.deprovision_bot(domain=domain, final_backup=final_backup)
    except mitseller.MitSellerError as exc:
        logger.warning("removing bot %s (%s) failed: %s", name, domain, exc)
        raise BotRemovalError(str(exc)) from exc

    with engin.sessionLocal() as session:
        crud.remove_bot(session, bot_id)
    logger.info("bot %s (%s) removed from its server and the panel", name, domain)
    return {"name": name, "domain": domain}
