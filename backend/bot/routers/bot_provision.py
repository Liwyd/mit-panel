"""Building a mit-seller bot from the panel.

Three things live here:

* after a reseller panel is created, the superadmin is asked whether they want
  a Telegram bot for it too, and if so the bot is installed on the mit-seller
  server and handed over;
* the same flow is reachable for an admin that already exists;
* a buyer who bought a panel can ask for a bot of their own. That one only
  records the request and tells the superadmin — the token and the domain are
  theirs to supply, because the bot runs on infrastructure they control.

Every one of these ends in an HTTP call to the mit-seller server's
provisioning API: the panel runs in a container with no shell and no SSH, so
asking is the only thing it can do.
"""

from __future__ import annotations

import re
import socket

import httpx
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import db, keyboards, texts
from backend.bot.config import bot_config as settings
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import ALL_MENU_TEXTS, menu_kb_for, remember_section, superadmin_kb
from backend.bot.states import CreateBot, CreateBotPickAdmin
from backend.db import crud
from backend.db.engin import sessionLocal
from backend.utils import mitseller
from backend.utils.logger import logger
from backend.utils.settings_store import get_settings

router = Router(name="bot_provision")

# A BotFather token: a numeric id, a colon, then the secret. The mit-seller
# server validates this again — this only catches a typo before a minute of
# certbot is spent on it.
TOKEN_RE = re.compile(r"^\d{3,20}:[A-Za-z0-9_-]{30,}$")
# A hostname: no scheme, no path, no port, nothing a shell would notice.
DOMAIN_RE = re.compile(
    r"^(?=.{1,253}$)[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?(\.[a-z0-9]([a-z0-9-]{0,61}[a-z0-9])?)+$"
)
IPV4_RE = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
TELEGRAM_API = "https://api.telegram.org"


def _is_superadmin(user_id: int) -> bool:
    return user_id in settings.superadmin_id_list


# ---------------------------------------------------------------- starting


async def ask_token(
    message: Message,
    state: FSMContext,
    admin_id: int,
    admin_username: str,
    admin_telegram_id: int | None = None,
    request_id: int | None = None,
) -> None:
    """Ask for the BotFather token, remembering who this bot is for."""
    data: dict = {"bot_admin_id": admin_id, "bot_admin_username": admin_username}
    if admin_telegram_id:
        # The Telegram id of the person this bot is for: they are made an
        # admin of it after the install. `bot_admin_id` is this panel's own
        # row id — the mit-seller server would write that number into the bot
        # as its admin, and it would belong to nobody.
        data["bot_admin_telegram_id"] = admin_telegram_id
    if request_id is not None:
        data["bot_request_id"] = request_id
    await state.set_data(data)
    await state.set_state(CreateBot.token)
    await message.answer(texts.ASK_BOT_TOKEN, reply_markup=keyboards.cancel_kb())


async def _continue_for_admin(message: Message, state: FSMContext, admin) -> None:
    """Go on towards the token for an existing admin.

    Their Telegram id is what makes them an admin of the bot once it is
    built. When their row has none it is asked for here instead of guessed:
    the superadmin knows it, and the person the bot is built for has to be
    able to use it.
    """
    if admin.telegram_id:
        await ask_token(message, state, admin.id, admin.username, admin.telegram_id)
        return
    await state.set_state(CreateBotPickAdmin.telegram_id)
    await state.set_data({"bot_admin_id": admin.id, "bot_admin_username": admin.username})
    await message.answer(
        texts.ASK_ADMIN_TELEGRAM_ID.format(username=admin.username),
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(CreateBotPickAdmin.telegram_id, ~F.text.in_(ALL_MENU_TEXTS))
async def got_admin_telegram_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.isdigit():
        await message.answer(
            texts.ASK_ADMIN_TELEGRAM_ID_BAD, reply_markup=keyboards.cancel_kb()
        )
        return
    data = await state.get_data()
    await ask_token(
        message,
        state,
        int(data["bot_admin_id"]),
        data.get("bot_admin_username") or "",
        admin_telegram_id=int(raw),
    )


@router.message(F.text == texts.BTN_CREATE_BOT_FOR_ADMIN, SuperadminFilter())
async def start_pick_admin(message: Message, state: FSMContext) -> None:
    remember_section(message.from_user.id, "panels")
    if not mitseller.provision_configured():
        await message.answer(texts.BOT_NOT_CONFIGURED, reply_markup=superadmin_kb(message.from_user.id))
        return
    with sessionLocal() as session:
        admins = [a for a in crud.get_all_admins(session) if a.is_active]
    if not admins:
        await message.answer(texts.NO_ADMINS_FOR_BOT, reply_markup=superadmin_kb(message.from_user.id))
        return
    await state.set_state(CreateBotPickAdmin.admin)
    await message.answer(
        texts.ASK_PICK_ADMIN_FOR_BOT,
        reply_markup=keyboards.admin_picker_kb(admins, "bot_admin"),
    )


@router.callback_query(CreateBotPickAdmin.admin, F.data.startswith("bot_admin:"))
async def picked_admin(call: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(call.from_user.id):
        await call.answer()
        return
    admin_id = int(call.data.split(":", 1)[1])
    with sessionLocal() as session:
        admin = crud.get_admin_by_id(session, admin_id)
    if admin is None:
        await call.answer("این ساب‌ادمین دیگر وجود ندارد", show_alert=True)
        return
    await call.answer()
    await state.clear()
    await _continue_for_admin(call.message, state, admin)


@router.callback_query(F.data.startswith("bot_make:"))
async def make_bot_for_new_admin(call: CallbackQuery, state: FSMContext) -> None:
    """The «yes» after a new panel was created."""
    if not _is_superadmin(call.from_user.id):
        await call.answer()
        return
    admin_id = int(call.data.split(":", 1)[1])
    with sessionLocal() as session:
        admin = crud.get_admin_by_id(session, admin_id)
    if admin is None:
        await call.answer("این ساب‌ادمین دیگر وجود ندارد", show_alert=True)
        return
    await call.answer()
    await state.clear()
    await _continue_for_admin(call.message, state, admin)


@router.callback_query(F.data == "bot_skip")
async def skip_bot(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("باشه")
    if _is_superadmin(call.from_user.id):
        await call.message.answer(
            texts.BOT_SKIPPED, reply_markup=superadmin_kb(call.from_user.id)
        )


# ---------------------------------------------------------------- collecting


@router.message(CreateBot.token, ~F.text.in_(ALL_MENU_TEXTS))
async def got_token(message: Message, state: FSMContext) -> None:
    token = (message.text or "").strip()
    username = ""
    if TOKEN_RE.match(token):
        try:
            async with httpx.AsyncClient(timeout=httpx.Timeout(15.0, connect=8.0)) as client:
                res = await client.get(f"{TELEGRAM_API}/bot{token}/getMe")
            username = str((res.json().get("result") or {}).get("username") or "")
        except (httpx.HTTPError, ValueError):
            username = ""
    if not username:
        await message.answer(texts.ASK_BOT_TOKEN_BAD, reply_markup=keyboards.cancel_kb())
        return
    await state.update_data(bot_token=token, bot_username=username)
    await state.set_state(CreateBot.domain)
    await message.answer(texts.ASK_BOT_DOMAIN, reply_markup=keyboards.cancel_kb())


def _domain_points_here(domain: str) -> bool:
    """Does the domain resolve to the mit-seller server?

    A wrong answer costs a minute of certbot and a confusing failure, so it is
    worth asking before anything is installed. An address setting is compared
    exactly; a hostname is compared against whatever it resolves to.
    """
    server = (get_settings().get("mitseller_server") or "").strip()
    try:
        answers = {item[4][0] for item in socket.getaddrinfo(domain, 443, proto=socket.IPPROTO_TCP)}
    except OSError:
        return False
    if not answers:
        return False
    if not server or server == "localhost":
        return True
    if IPV4_RE.fullmatch(server):
        return server in answers
    try:
        targets = {item[4][0] for item in socket.getaddrinfo(server, 443, proto=socket.IPPROTO_TCP)}
    except OSError:
        return True  # cannot tell; let the server itself refuse
    return bool(answers & targets)


@router.message(CreateBot.domain, ~F.text.in_(ALL_MENU_TEXTS))
async def got_domain(message: Message, state: FSMContext, bot) -> None:
    domain = (message.text or "").strip().lower().rstrip(".")
    if not DOMAIN_RE.match(domain) or "--" in domain:
        await message.answer(texts.ASK_BOT_DOMAIN_BAD, reply_markup=keyboards.cancel_kb())
        return
    if not _domain_points_here(domain):
        await message.answer(
            texts.BOT_NO_DNS.format(domain=domain), reply_markup=keyboards.cancel_kb()
        )
        return

    data = await state.get_data()
    await state.clear()
    await message.answer(texts.BOT_INSTALLING, reply_markup=superadmin_kb(message.from_user.id))
    await _install(
        message,
        bot,
        domain=domain,
        token=data["bot_token"],
        admin_id=int(data.get("bot_admin_id") or 0),
        owner_telegram_id=int(data.get("bot_admin_telegram_id") or 0),
        request_id=data.get("bot_request_id"),
    )


# ---------------------------------------------------------------- installing


async def _install(
    message: Message,
    bot,
    *,
    domain: str,
    token: str,
    admin_id: int,
    owner_telegram_id: int = 0,
    request_id: int | None = None,
) -> None:
    admin = None
    panel_url = ""
    if admin_id:
        with sessionLocal() as session:
            admin = crud.get_admin_by_id(session, admin_id)
            # The Marzban address this reseller sells from, by panel name.
            if admin is not None and admin.panel:
                for p in crud.get_all_panels(session):
                    if p.name == admin.panel:
                        panel_url = p.url
                        break

    # The bot's main admin is the superadmin who asked for it — that is the
    # one id the bot's API refuses to remove, and nothing gets built without a
    # superadmin. Whoever the bot is *for* (the admin picked for it, the buyer
    # behind a request) is added as an ordinary admin right after, so that
    # access can be granted or taken back later without touching the server.
    # `admin_id` is this panel's row id, not a Telegram id: written into the
    # bot it would be an admin of nobody.
    owner_id = int(message.from_user.id)
    for_admin_id = owner_telegram_id or (
        int(admin.telegram_id) if admin is not None and admin.telegram_id else 0
    )

    try:
        result = await mitseller.provision_bot(
            token=token,
            domain=domain,
            admin_id=owner_id,
            cert_email=(get_settings().get("mitseller_cert_email") or "").strip(),
        )
    except mitseller.MitSellerError as exc:
        await message.answer(
            texts.BOT_INSTALL_FAILED.format(error=exc),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return

    url = str(result.get("url") or f"https://{domain}")
    owner_key = str(result.get("owner_key") or "")
    manager_key = str(result.get("manager_key") or "")
    mit_secret = str(result.get("mit_secret") or "")
    bot_username = str(result.get("bot_username") or "")
    bot_link = f"https://t.me/{bot_username}" if bot_username else url

    # Record it here so it shows up under Bot → اتصال ربات‌ها. install.sh asks
    # the panel to do this too, but a failure there must not lose the bot.
    assigned_to = str(result.get("assigned_to") or "")
    if not result.get("registered"):
        _record_bot(url, owner_key, manager_key, bot_username, admin.id if admin else None)

    # The person the bot was built for gets their own admin on it, once the
    # install is done: the main admin is fixed in the bot's config, and only
    # the ones after them can be added or removed over the API.
    admin_note = ""
    if for_admin_id and for_admin_id != owner_id:
        try:
            await mitseller.add_bot_admin(bot_url=url, owner_key=owner_key, admin_id=for_admin_id)
            admin_note = texts.BOT_ADMIN_ADDED.format(admin_id=for_admin_id)
        except mitseller.MitSellerError as exc:
            admin_note = texts.BOT_ADMIN_FAILED.format(error=exc)
            logger.warning(f"admin {for_admin_id} not added to {url}: {exc}")

    panel_note = ""
    if admin is not None and panel_url and admin.marzban_password:
        try:
            panel_note = await mitseller.push_vip_panel(
                bot_url=url,
                owner_key=owner_key,
                username=admin.username,
                password=admin.marzban_password,
                panel_url=panel_url,
            )
        except mitseller.MitSellerError as exc:
            panel_note = texts.BOT_PANEL_FAILED.format(error=exc)
            logger.warning(f"VIP panel not pushed to {url}: {exc}")
    elif admin is not None:
        panel_note = texts.BOT_NO_PANEL_PASSWORD.format(username=admin.username)

    if request_id:
        db.mark_bot_request_reviewed(
            int(request_id), "approved", message.from_user.id, admin_id=admin.id if admin else None
        )

    await message.answer(
        texts.BOT_DONE_SUPERADMIN.format(
            bot_username=bot_username or "—",
            bot_link=bot_link,
            url=url,
            n=result.get("n", "?"),
            admin_id=owner_id,
            mit_secret=mit_secret,
            owner_key=owner_key,
            manager_key=manager_key,
        ),
        reply_markup=superadmin_kb(message.from_user.id),
    )
    if admin_note:
        await message.answer(admin_note, reply_markup=superadmin_kb(message.from_user.id))
    if panel_note:
        await message.answer(panel_note, reply_markup=superadmin_kb(message.from_user.id))
    if assigned_to:
        await message.answer(
            texts.BOT_REGISTERED_AS.format(assigned_to=assigned_to),
            reply_markup=superadmin_kb(message.from_user.id),
        )

    # The reseller gets the bot separately from the panel, which is the point.
    if admin is not None and admin.telegram_id:
        try:
            await bot.send_message(
                int(admin.telegram_id),
                texts.BOT_DONE_ADMIN.format(
                    bot_link=bot_link,
                    bot_username=bot_username or "—",
                    mit_secret=mit_secret,
                ),
            )
        except Exception:
            pass


def _record_bot(url: str, owner_key: str, manager_key: str, bot_username: str, admin_id: int | None) -> None:
    with sessionLocal() as session:
        existing = next((b for b in crud.get_all_bots(session) if b.url == url), None)
        if existing:
            crud.update_bot(
                session,
                existing,
                owner_key=owner_key,
                manager_key=manager_key,
                bot_username=bot_username or existing.bot_username,
                admin_id=admin_id if admin_id else existing.admin_id,
            )
            return
        crud.add_bot(
            session,
            name=f"@{bot_username}" if bot_username else url,
            url=url,
            owner_key=owner_key,
            manager_key=manager_key,
            admin_id=admin_id,
            bot_username=bot_username,
            is_active=True,
        )


# ---------------------------------------------------------------- R3: a buyer asking


@router.message(F.text == texts.BTN_REQUEST_BOT)
async def request_bot(message: Message) -> None:
    """A buyer asking for a bot. Records it and tells the superadmin; nothing
    is provisioned without a token and a domain, and only the superadmin has
    those."""
    user_id = message.from_user.id
    if _is_superadmin(user_id):
        await message.answer(texts.BOT_REQUEST_AS_SUPERADMIN, reply_markup=superadmin_kb(user_id))
        return
    if db.get_pending_bot_request(user_id):
        await message.answer(texts.BOT_REQUEST_PENDING, reply_markup=await menu_kb_for(user_id))
        return
    db.create_bot_request(user_id, message.from_user.username)
    await message.answer(texts.BOT_REQUEST_RECEIVED, reply_markup=await menu_kb_for(user_id))
    name = message.from_user.full_name or message.from_user.username or str(user_id)
    text = texts.BOT_REQUEST_REVIEW.format(name=name, telegram_id=user_id)
    for superadmin_id in settings.superadmin_id_list:
        try:
            await message.bot.send_message(superadmin_id, text)
        except Exception:
            continue


@router.message(F.text == texts.BTN_BOT_REQUESTS, SuperadminFilter())
async def list_bot_requests(message: Message) -> None:
    remember_section(message.from_user.id, "panels")
    requests = db.list_pending_bot_requests()
    if not requests:
        await message.answer(texts.NO_BOT_REQUESTS, reply_markup=superadmin_kb(message.from_user.id))
        return
    await message.answer(
        texts.ASK_PICK_BOT_REQUEST, reply_markup=keyboards.bot_requests_kb(requests)
    )


@router.callback_query(F.data.startswith("bot_req:"))
async def open_bot_request(call: CallbackQuery, state: FSMContext) -> None:
    if not _is_superadmin(call.from_user.id):
        await call.answer()
        return
    request_id = int(call.data.split(":", 1)[1])
    req = db.get_bot_request(request_id)
    if req is None or req.get("status") != "pending":
        await call.answer(texts.NO_BOT_REQUEST, show_alert=True)
        return
    await call.answer()
    # A buyer is not a panel admin, so the bot is built for their own Telegram
    # id. They have no reseller panel, so there is nothing to push into it.
    await ask_token(
        call.message,
        state,
        int(req["telegram_id"]),
        req.get("username") or "",
        admin_telegram_id=int(req["telegram_id"]),
        request_id=request_id,
    )
