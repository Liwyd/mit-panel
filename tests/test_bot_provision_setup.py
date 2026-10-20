"""How a new mit-seller bot is set up: its management code and its panel.

Two things the superadmin is promised when a bot is built:

* the code that opens the bot's panel section is the one they chose — it is
  written into the bot's config, so a code the server would refuse has to be
  refused here, before a minute of certbot is spent on it;
* the bot's own panel list already holds the reseller's mit-panel and the
  Marzban behind it, so that after the install there is nothing left to add
  by hand. The bot signs in to that panel as the reseller, so the credential
  is checked first: a bot carrying a panel it cannot sign in to sells nothing.
"""

import asyncio
from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot.routers import bot_provision
from backend.bot.states import CreateBot
from backend.db import crud
from backend.db.model import Admins
from backend.utils import mitseller

SUPERADMIN = 1451599691


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


def make_state() -> FSMContext:
    storage = MemoryStorage()
    return FSMContext(storage=storage, key=StorageKey(chat_id=1, user_id=1, bot_id=1))


def _run(coroutine):
    return asyncio.run(coroutine)


def _add_admin(db_session, username: str, *, panel: str = "", marzban_password: str = ""):
    row = Admins(
        username=username,
        hashed_password="x",
        telegram_id=7000000001,
        panel=panel,
        marzban_password=marzban_password or None,
        is_active=True,
    )
    db_session.add(row)
    db_session.commit()
    return crud.get_admin_by_username(db_session, username)


def _patch(monkeypatch, *, verify=True, mit_fails=False):
    """Stub the bot server and the panel's own login check."""
    seen: dict = {"provision": {}, "mit": [], "vip": []}

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
        return None

    async def fake_push_mit_panel(**kwargs):
        if mit_fails:
            raise mitseller.MitSellerError("refused")
        seen["mit"].append(kwargs)
        return "ok"

    async def fake_push_vip_panel(**kwargs):
        seen["vip"].append(kwargs)
        return "ok"

    async def fake_verify(panel_base, username, password):
        return verify

    monkeypatch.setattr(mitseller, "provision_bot", fake_provision)
    monkeypatch.setattr(mitseller, "add_bot_admin", fake_add_admin)
    monkeypatch.setattr(mitseller, "push_mit_panel", fake_push_mit_panel)
    monkeypatch.setattr(mitseller, "push_vip_panel", fake_push_vip_panel)
    monkeypatch.setattr(mitseller, "verify_panel_login", fake_verify)
    return seen


def _install(monkeypatch, admin, **kwargs):
    seen = _patch(monkeypatch, **kwargs.pop("_patch", {}))
    _run(
        bot_provision._install(
            FakeMessage(SUPERADMIN),
            FakeBot(),
            domain="new.example.com",
            token="123:AAH",
            admin_id=admin.id if admin else 0,
            **kwargs,
        )
    )
    return seen


# ------------------------------------------------------------------ the code


def test_the_code_the_superadmin_chose_is_the_one_the_bot_gets(db_session, monkeypatch):
    admin = _add_admin(db_session, "seller")

    seen = _install(monkeypatch, admin, mit_secret="MyCode123")

    assert seen["provision"]["mit_secret"] == "MyCode123"


def test_a_code_the_server_would_refuse_is_not_accepted(db_session):
    state = make_state()
    _run(state.set_state(CreateBot.secret))

    for bad in ("short", "with space", "a" * 129, "semi;colon"):
        _run(bot_provision.got_bot_secret(FakeMessage(SUPERADMIN, bad), state, FakeBot()))
        assert _run(state.get_state()) == CreateBot.secret.state
        assert _run(state.get_data()).get("bot_mit_secret") is None


def test_a_good_code_is_kept_and_the_domain_comes_next(db_session):
    state = make_state()
    _run(state.set_state(CreateBot.secret))

    _run(bot_provision.got_bot_secret(FakeMessage(SUPERADMIN, "MyCode123"), state, FakeBot()))

    assert _run(state.get_state()) == CreateBot.domain.state
    assert _run(state.get_data())["bot_mit_secret"] == "MyCode123"


# ----------------------------------------------------------------- the panel


def test_the_bots_panel_list_gets_the_resellers_own_panel(
    db_session, monkeypatch, marzban_panel
):
    admin = _add_admin(
        db_session, "seller", panel=marzban_panel.name, marzban_password="reseller-pass"
    )

    seen = _install(monkeypatch, admin)

    assert len(seen["mit"]) == 1
    pushed = seen["mit"][0]
    assert pushed["panel_user"] == "seller"
    assert pushed["panel_password"] == "reseller-pass"
    assert pushed["panel_url"].endswith("/panpan")
    assert pushed["marzban_url"] == marzban_panel.url
    assert pushed["marzban_user"] == "seller"
    assert pushed["marzban_password"] == "reseller-pass"
    # One panel, not two: the mit-panel replaces the plain one.
    assert seen["vip"] == []


def test_a_mit_panel_that_cannot_be_made_falls_back_to_the_plain_one(
    db_session, monkeypatch, marzban_panel
):
    admin = _add_admin(
        db_session, "seller", panel=marzban_panel.name, marzban_password="reseller-pass"
    )

    seen = _install(monkeypatch, admin, _patch={"mit_fails": True})

    assert seen["mit"] == []
    assert len(seen["vip"]) == 1
    assert seen["vip"][0]["panel_url"] == marzban_panel.url


def test_a_reseller_without_a_marzban_password_gets_no_panel(db_session, monkeypatch):
    admin = _add_admin(db_session, "seller")

    seen = _install(monkeypatch, admin)

    assert seen["mit"] == []
    assert seen["vip"] == []


def test_the_resellers_password_is_checked_before_the_bot_is_built(
    db_session, monkeypatch, marzban_panel
):
    admin = _add_admin(
        db_session, "seller", panel=marzban_panel.name, marzban_password="reseller-pass"
    )
    _patch(monkeypatch, verify=False)
    state = make_state()
    _run(state.set_data({"bot_admin_id": admin.id}))
    message = FakeMessage(SUPERADMIN)

    ready = _run(bot_provision._settle_panel_password(message, state))

    # The panel refused that password, so the superadmin is asked for the
    # real one instead of a bot being built with a dead panel.
    assert ready is False
    assert _run(state.get_state()) == CreateBot.panel_password.state
    assert any("seller" in answer for answer in message.answers)


def test_a_working_password_is_kept_and_needs_no_question(
    db_session, monkeypatch, marzban_panel
):
    admin = _add_admin(
        db_session, "seller", panel=marzban_panel.name, marzban_password="reseller-pass"
    )
    _patch(monkeypatch, verify=True)
    state = make_state()
    _run(state.set_data({"bot_admin_id": admin.id}))

    ready = _run(bot_provision._settle_panel_password(FakeMessage(SUPERADMIN), state))

    assert ready is True
    data = _run(state.get_data())
    assert data["panel_cred"] == {"user": "seller", "pass": "reseller-pass"}
    assert _run(state.get_state()) is None


def test_the_password_the_superadmin_gives_is_used_for_the_bot(
    db_session, monkeypatch, marzban_panel
):
    admin = _add_admin(
        db_session, "seller", panel=marzban_panel.name, marzban_password="reseller-pass"
    )
    seen = _patch(monkeypatch, verify=True)
    state = make_state()
    _run(
        state.set_data(
            {
                "bot_admin_id": admin.id,
                "bot_domain": "new.example.com",
                "bot_token": "123:AAH",
                "bot_mit_secret": "MyCode123",
            }
        )
    )
    _run(state.set_state(CreateBot.panel_password))

    _run(
        bot_provision.got_panel_password(
            FakeMessage(SUPERADMIN, "the-real-one"), state, FakeBot()
        )
    )

    assert seen["provision"]["mit_secret"] == "MyCode123"
    assert seen["mit"][0]["panel_password"] == "the-real-one"
