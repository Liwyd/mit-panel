"""Who a new mit-seller bot belongs to, and the address its certificate uses.

The bot's main admin is written into its config at install time and the bot's
API refuses to remove it, so that name belongs to the superadmin who issued the
build command — whoever else is involved (the sub-admin the bot was built for,
the buyer behind a request) is added as an ordinary admin afterwards and can be
removed again later. Before this, the panel sent its own admin *row* id (16,
29, …) as the bot's admin — a number that is nobody — and then the sub-admin
whose panel it was ended up as the unremovable main admin instead
(production, 2026-10-20). The certificate email was never sent at all, so the
server refused to build anything (`CERT_EMAIL: set CERT_EMAIL=`); every bot's
certificate now goes to one address.
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


def _install(monkeypatch, admin, *, message=None, added=None, add_fails=False, **kwargs):
    """Run `_install` and return what the panel asked the server for.

    `added` collects whoever was given a second admin on the finished bot.
    """
    seen: dict = {}
    message = message or FakeMessage(SUPERADMIN)

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

    async def fake_add_admin(*, bot_url, owner_key, admin_id):
        if add_fails:
            raise mitseller.MitSellerError("refused")
        if added is not None:
            added.append((bot_url, owner_key, int(admin_id)))

    monkeypatch.setattr(mitseller, "provision_bot", fake_provision)
    monkeypatch.setattr(mitseller, "add_bot_admin", fake_add_admin)
    _run(
        bot_provision._install(
            message,
            FakeBot(),
            domain="new.example.com",
            token="123:AAH",
            admin_id=admin.id if admin else 0,
            **kwargs,
        )
    )
    return seen


def test_the_bot_belongs_to_the_superadmin_who_asked_for_it(db_session, monkeypatch):
    admin = _add_admin(db_session, "seller", 6900787101)

    seen = _install(monkeypatch, admin)

    assert seen["admin_id"] == SUPERADMIN
    assert seen["admin_id"] != admin.id  # the row id is not a Telegram id
    assert seen["admin_id"] != 6900787101  # and not the admin it was built for


def test_the_admin_it_is_built_for_is_added_as_a_second_admin(db_session, monkeypatch):
    admin = _add_admin(db_session, "seller", 6900787101)
    added: list = []

    _install(monkeypatch, admin, added=added)

    assert added == [("https://new.example.com", "owner", 6900787101)]


def test_the_same_person_is_not_added_twice(db_session, monkeypatch):
    """Building a bot for the superadmin's own id needs nobody else on it."""
    admin = _add_admin(db_session, "seller", SUPERADMIN)
    added: list = []

    seen = _install(monkeypatch, admin, added=added)

    assert seen["admin_id"] == SUPERADMIN
    assert added == []


def test_the_certificate_goes_to_the_one_address(db_session, monkeypatch):
    admin = _add_admin(db_session, "seller", 6900787101)

    seen = _install(monkeypatch, admin)

    assert seen["cert_email"] == "mitgetcert@gmail.com"
    assert seen["cert_email"] == get_settings()["mitseller_cert_email"]


def test_a_row_without_a_telegram_id_belongs_to_whoever_builds_it(
    db_session, monkeypatch
):
    admin = _add_admin(db_session, "no-telegram-id", None)
    added: list = []

    seen = _install(monkeypatch, admin, added=added)

    assert seen["admin_id"] == SUPERADMIN
    assert added == []  # nobody known to add


def test_an_explicit_owner_keeps_admin_on_the_bot(db_session, monkeypatch):
    """A buyer's request carries their own id: the bot is theirs to run."""
    admin = _add_admin(db_session, "seller", 6900787101)
    added: list = []

    seen = _install(monkeypatch, admin, owner_telegram_id=7000000001, added=added)

    assert seen["admin_id"] == SUPERADMIN  # the superadmin built it, and keeps it
    assert added == [("https://new.example.com", "owner", 7000000001)]


def test_a_second_admin_that_cannot_be_added_does_not_lose_the_bot(
    db_session, monkeypatch
):
    admin = _add_admin(db_session, "seller", 6900787101)
    message = FakeMessage(SUPERADMIN)

    # No raise: the bot is installed and its keys are shown either way.
    _install(monkeypatch, admin, message=message, add_fails=True)

    assert any("6900787101" in answer or "refused" in answer for answer in message.answers)


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
