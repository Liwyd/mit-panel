"""Who a new mit-seller bot belongs to, and the address its certificate uses.

The bot's `ADMIN` is a Telegram id: install.sh writes it straight into the
bot's config, and whoever ends up there owns the bot. The panel's own admin
rows are keyed by an internal id, so sending that gave every bot an owner of
`16` or `29` — a number that is nobody. The certificate email was never sent
at all, so the server refused to build anything (`CERT_EMAIL: set CERT_EMAIL=`,
production, 2026-10-20); every bot's certificate now goes to one address.
"""

import asyncio
from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot.routers import bot_provision
from backend.bot.states import CreateBot, CreateBotPickAdmin
from backend.db import crud
from backend.db.model import Admins
from backend.utils import mitseller
from backend.utils.settings_store import get_settings

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


def _add_admin(db_session, username: str, telegram_id) -> Admins:
    row = Admins(
        username=username,
        hashed_password="x",
        telegram_id=telegram_id,
        panel="",
        is_active=True,
    )
    db_session.add(row)
    db_session.commit()
    return crud.get_admin_by_username(db_session, username)


def _run(coroutine):
    return asyncio.run(coroutine)


def _install(monkeypatch, admin, **kwargs):
    """Run `_install` and return what the panel asked the server for."""
    seen: dict = {}

    async def fake_provision(**kwargs_seen):
        seen.update(kwargs_seen)
        return {
            "url": "https://new.example.com",
            "owner_key": "owner",
            "manager_key": "manager",
            "mit_secret": "secret",
            "bot_username": "newbot",
            "n": 7,
        }

    monkeypatch.setattr(mitseller, "provision_bot", fake_provision)
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


def test_the_bot_is_built_for_the_admins_telegram_id(db_session, monkeypatch):
    admin = _add_admin(db_session, "seller", 6900787101)

    seen = _install(monkeypatch, admin)

    assert seen["admin_id"] == 6900787101
    assert seen["admin_id"] != admin.id  # the row id is not a Telegram id


def test_the_certificate_goes_to_the_one_address(db_session, monkeypatch):
    admin = _add_admin(db_session, "seller", 6900787101)

    seen = _install(monkeypatch, admin)

    assert seen["cert_email"] == "mitgetcert@gmail.com"
    assert seen["cert_email"] == get_settings()["mitseller_cert_email"]


def test_a_row_without_a_telegram_id_belongs_to_whoever_builds_it(
    db_session, monkeypatch
):
    admin = _add_admin(db_session, "no-telegram-id", None)

    seen = _install(monkeypatch, admin)

    assert seen["admin_id"] == SUPERADMIN


def test_an_explicit_owner_beats_the_row(db_session, monkeypatch):
    """A buyer's request carries their own id, and it is theirs to keep."""
    admin = _add_admin(db_session, "seller", 6900787101)

    seen = _install(monkeypatch, admin, owner_telegram_id=7000000001)

    assert seen["admin_id"] == 7000000001


def test_an_admin_with_an_id_goes_straight_to_the_token(db_session):
    admin = _add_admin(db_session, "seller", 6900787101)
    state, message = make_state(), FakeMessage(SUPERADMIN)

    _run(bot_provision._continue_for_admin(message, state, admin))

    assert _run(state.get_state()) == CreateBot.token.state
    assert _run(state.get_data())["bot_admin_telegram_id"] == 6900787101


def test_a_row_without_an_id_is_asked_for_theirs(db_session):
    admin = _add_admin(db_session, "no-telegram-id", None)
    state, message = make_state(), FakeMessage(SUPERADMIN)

    _run(bot_provision._continue_for_admin(message, state, admin))

    assert _run(state.get_state()) == CreateBotPickAdmin.telegram_id.state
    assert any("no-telegram-id" in answer for answer in message.answers)
    # Nothing has been built: the token is not asked for until the id is in.
    assert _run(state.get_data()).get("bot_token") is None

    # A number is taken, anything else is refused with the question again.
    _run(bot_provision.got_admin_telegram_id(FakeMessage(SUPERADMIN, "not a number"), state))
    assert _run(state.get_state()) == CreateBotPickAdmin.telegram_id.state

    _run(bot_provision.got_admin_telegram_id(FakeMessage(SUPERADMIN, " 7000000001 "), state))
    assert _run(state.get_state()) == CreateBot.token.state
    data = _run(state.get_data())
    assert data["bot_admin_telegram_id"] == 7000000001
    assert data["bot_admin_id"] == admin.id  # the row id is still there for us
