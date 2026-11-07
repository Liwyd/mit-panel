"""Building a bot for whoever asked for it over «درخواست ربات تلگрамی».

The request only carries a Telegram id, but the install wants this panel's
*row* id: `bot_admin_id` is looked up with `get_admin_by_id`, and the panel it
pushes into the bot and the owner it records both hang off that row. Handing
the Telegram id over instead resolves to no row at all, and the build then
comes out half finished — no panel in the bot's «مدیریت پنل‌ها» and nobody as
its owner, so the panel shows «فقط خودم» (production, @Drkhshnvpnbot,
2026-11-07). The requester is not always a plain buyer: a sub-admin of this
panel can ask too, and theirs has to come out the way a bot built from their
own row does.
"""

import asyncio
from types import SimpleNamespace

import pytest

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot.config import bot_config
from backend.bot.routers import bot_provision
from backend.db import crud
from backend.db.model import Admins
from backend.utils import mitseller

SUPERADMIN = 1451599691
# The sub-admin behind the bot this was written for.
SUB_ADMIN = 1192631401
MIT_BASE = "https://panel.example/panpan"


class FakeMessage:
    def __init__(self, user_id: int = SUPERADMIN, text: str = "") -> None:
        self.from_user = SimpleNamespace(id=user_id)
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append(text)
        return self


class FakeBot:
    def __init__(self) -> None:
        self.sent: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((int(chat_id), text))


class FakeCall:
    """The tap on one row of «درخواست‌های باز ربات»."""

    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=SUPERADMIN)
        self.message = FakeMessage()
        self.answered: list[tuple[str, bool]] = []

    async def answer(self, text=None, show_alert: bool = False, **kwargs):
        self.answered.append((text or "", show_alert))


def make_state() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(chat_id=1, user_id=1, bot_id=1))


@pytest.fixture(autouse=True)
def _superadmin(monkeypatch):
    """Let the handler past its gate.

    `superadmin_id_list` is read from panel settings no test sets, and the
    gate itself is not what any of these are about.
    """
    monkeypatch.setattr(bot_provision, "_is_superadmin", lambda user_id: True)


def _run(coroutine):
    return asyncio.run(coroutine)


def _add_admin(db_session, username: str, telegram_id, *, panel: str, password: str):
    admin = Admins(
        username=username,
        hashed_password="x",
        telegram_id=telegram_id,
        panel=panel,
        marzban_password=password,
        is_active=True,
    )
    db_session.add(admin)
    db_session.commit()
    return crud.get_admin_by_username(db_session, username)


def _open_request(state, request_id: int) -> FakeCall:
    call = FakeCall(f"bot_req:{request_id}")
    _run(bot_provision.open_bot_request(call, state))
    return call


def _patch(monkeypatch, seen: dict) -> None:
    """Stub every conversation with the bot server and the panel's login."""

    async def fake_provision(**kwargs):
        seen["provision"] = kwargs
        return {
            "url": "https://new.example.com",
            "owner_key": "owner",
            "manager_key": "manager",
            "mit_secret": kwargs.get("mit_secret") or "",
            "bot_username": "newbot",
            "n": 7,
        }

    async def fake_add_admin(*, bot_url, owner_key, admin_id):
        seen.setdefault("added", []).append((bot_url, owner_key, int(admin_id)))

    async def fake_push_mit_panel(**kwargs):
        seen.setdefault("mit", []).append(kwargs)
        return "ok"

    async def fake_push_vip_panel(**kwargs):
        seen.setdefault("vip", []).append(kwargs)
        return "ok"

    async def fake_bind(*, bot_url, owner_key, panel_name):
        seen.setdefault("bound", []).append(panel_name)
        return 6

    async def fake_verify(panel_base, username, password):
        return True

    monkeypatch.setattr(mitseller, "provision_bot", fake_provision)
    monkeypatch.setattr(mitseller, "add_bot_admin", fake_add_admin)
    monkeypatch.setattr(mitseller, "push_mit_panel", fake_push_mit_panel)
    monkeypatch.setattr(mitseller, "push_vip_panel", fake_push_vip_panel)
    monkeypatch.setattr(mitseller, "bind_products_to_panel", fake_bind)
    monkeypatch.setattr(mitseller, "verify_panel_login", fake_verify)
    monkeypatch.setattr(bot_provision, "_mit_panel_base", lambda: MIT_BASE)


# ------------------------------------------------------------- what is asked


def test_a_sub_admins_request_is_built_from_their_panel_row(db_session, ledger):
    admin = _add_admin(db_session, "drkhshn", SUB_ADMIN, panel="touch", password="pw")
    request_id = ledger.create_bot_request(SUB_ADMIN, "Rezadrkhshn1")
    state = make_state()

    _open_request(state, request_id)

    data = _run(state.get_data())
    # The row id, not the Telegram id: this is what the install looks up.
    assert data["bot_admin_id"] == admin.id
    assert data["bot_admin_id"] != SUB_ADMIN
    assert data["bot_admin_telegram_id"] == SUB_ADMIN
    assert data["bot_request_id"] == request_id
    assert data["bot_admin_username"] == "drkhshn"


def test_a_buyer_with_no_panel_row_is_still_asked_for_a_token(db_session, ledger):
    request_id = ledger.create_bot_request(7000000099, "plainbuyer")
    state = make_state()

    _open_request(state, request_id)

    data = _run(state.get_data())
    # No row of theirs exists, so there is nothing to resolve and nothing to
    # push — but their Telegram id is still what makes them an admin of it.
    assert data["bot_admin_id"] == 0
    assert data["bot_admin_id"] != 7000000099
    assert data["bot_admin_telegram_id"] == 7000000099
    assert _run(state.get_state()) == bot_provision.CreateBot.token.state


def test_a_request_that_is_no_longer_open_is_refused(db_session, ledger):
    request_id = ledger.create_bot_request(SUB_ADMIN, "Rezadrkhshn1")
    ledger.mark_bot_request_reviewed(request_id, "approved", SUPERADMIN, admin_id=1)
    state = make_state()

    call = _open_request(state, request_id)

    assert call.answered and call.answered[0][1] is True
    assert _run(state.get_data()) == {}


# ------------------------------------- the whole thing, request to finished bot


def test_a_sub_admins_request_ends_with_their_panel_and_their_ownership(
    db_session, ledger, monkeypatch, marzban_panel
):
    """Both things that went missing on @Drkhshnvpnbot, in one run.

    The request goes in as a Telegram id and the build has to come out with the
    reseller's mit-panel in the bot's panel list, the shop items bound to it,
    and the bot recorded as belonging to their row.
    """
    admin = _add_admin(
        db_session,
        "drkhshn",
        SUB_ADMIN,
        panel=marzban_panel.name,
        password="reseller-pass",
    )
    request_id = ledger.create_bot_request(SUB_ADMIN, "Rezadrkhshn1")
    state = make_state()
    _open_request(state, request_id)
    seen: dict = {}
    _patch(monkeypatch, seen)

    _run(bot_provision._start_install(FakeMessage(SUPERADMIN), state, FakeBot()))

    # 1. the panel is in the bot's «مدیریت پنل‌ها»
    assert [row["name"] for row in seen.get("mit", [])] == ["پنل VIP مولتی لوکیشن"]
    assert seen["mit"][0]["panel_user"] == "drkhshn"
    assert seen["mit"][0]["marzban_url"] == marzban_panel.url
    assert seen.get("vip", []) == []  # the mit panel replaces the plain one
    # 2. the shop items are sold from it
    assert seen.get("bound") == ["پنل VIP مولتی لوکیشن"]
    # 3. the bot belongs to their row, not to nobody
    bots = crud.get_all_bots(db_session)
    assert [b.url for b in bots] == ["https://new.example.com"]
    assert bots[0].admin_id == admin.id
    # 4. the sub-admin is a second admin of the bot, and the request says so
    assert seen.get("added") == [("https://new.example.com", "owner", SUB_ADMIN)]
    reviewed = ledger.get_bot_request(request_id)
    assert reviewed["status"] == "approved"
    assert reviewed["admin_id"] == admin.id


def test_a_buyers_request_still_builds_a_bot_nobody_owns(
    db_session, ledger, monkeypatch, marzban_panel
):
    """The buyer path is unchanged: no row, no panel, nobody recorded."""
    request_id = ledger.create_bot_request(7000000099, "plainbuyer")
    state = make_state()
    _open_request(state, request_id)
    seen: dict = {}
    _patch(monkeypatch, seen)

    _run(bot_provision._start_install(FakeMessage(SUPERADMIN), state, FakeBot()))

    assert seen.get("mit", []) == []
    assert seen.get("vip", []) == []
    bots = crud.get_all_bots(db_session)
    assert [b.admin_id for b in bots] == [None]
    assert seen.get("added") == [("https://new.example.com", "owner", 7000000099)]
    assert ledger.get_bot_request(request_id)["admin_id"] is None
