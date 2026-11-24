"""A Marzban panel username may never contain whitespace.

Telegram lets people paste names carrying spaces, tabs or invisible Unicode
spaces, and the bot asks for a panel username in three flows (the shop
purchase, the superadmin admin form and the superadmin panel form).  The
username is an identifier on the panel and inside subscription URLs, so every
entry point is covered here: the handlers that accept the text, the
`panel_client` functions that write it, and the schema that guards the bot's
HTTP endpoint.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from pydantic import ValidationError

from backend.bot import panel_client, texts, validation
from backend.bot.routers import admin_settings, shop
from backend.schema._input import BotCreateAdminInput
from backend.services.marzban import api as marzban_api


# ── the primitive ──────────────────────────────────────────────────────────

@pytest.mark.parametrize(
    "value,expected",
    [
        ("reseller_1", False),
        ("reseller.one-2", False),
        ("reseller one", True),
        ("reseller\tone", True),
        ("reseller one ", True),
        ("reseller\u00a0one", True),
    ],
)
def test_has_space_detects_every_whitespace_character(value, expected):
    assert validation.has_space(value) is expected


# ── the bot handlers ───────────────────────────────────────────────────────

def _pair(text):
    """A message and its FSM state, with the async side channels recorded."""
    message = SimpleNamespace(text=text, answer=AsyncMock())
    state = SimpleNamespace(
        update_data=AsyncMock(), set_state=AsyncMock(), get_data=AsyncMock()
    )
    return message, state


def test_shop_username_with_a_space_is_refused_before_the_panel_is_looked_up(monkeypatch):
    message, state = _pair("my panel user")
    lookup = AsyncMock(return_value=False)
    monkeypatch.setattr(panel_client, "check_username_taken", lookup)

    asyncio.run(shop.shop_get_username(message, state))

    assert message.answer.await_args.args[0] == texts.USERNAME_INVALID
    lookup.assert_not_awaited()
    state.update_data.assert_not_awaited()
    state.set_state.assert_not_awaited()


def test_shop_username_without_a_space_moves_on(monkeypatch):
    message, state = _pair("  User_1 ")
    monkeypatch.setattr(panel_client, "check_username_taken", AsyncMock(return_value=False))

    asyncio.run(shop.shop_get_username(message, state))

    state.update_data.assert_awaited_once_with(shop_username="user_1")
    state.set_state.assert_awaited_once()


def test_create_admin_username_with_a_space_is_refused(monkeypatch):
    message, state = _pair("my panel user")
    lookup = AsyncMock(return_value=False)
    monkeypatch.setattr(panel_client, "check_username_taken", lookup)

    asyncio.run(admin_settings.create_admin_username(message, state))

    assert message.answer.await_args.args[0] == texts.USERNAME_INVALID
    lookup.assert_not_awaited()
    state.update_data.assert_not_awaited()


def test_create_panel_sudo_username_with_a_space_is_refused():
    message, state = _pair("sudo user")

    asyncio.run(admin_settings.create_panel_username(message, state))

    assert message.answer.await_args.args[0] == texts.USERNAME_NO_SPACE
    state.update_data.assert_not_awaited()
    state.set_state.assert_not_awaited()


# ── the write boundary ─────────────────────────────────────────────────────

@pytest.fixture()
def marzban_never_contacted(monkeypatch):
    """Any attempt to build a Marzban client fails the test loudly."""

    def factory(*args, **kwargs):
        raise AssertionError("Marzban must not be contacted for a spaced username")

    monkeypatch.setattr(marzban_api, "APIService", factory)


def test_create_admin_refuses_a_username_with_a_space(
    marzban_never_contacted, panel_client, admin_row
):
    with pytest.raises(panel_client.PanelClientError, match="English letters"):
        asyncio.run(
            panel_client.create_admin(
                username="bad name",
                password="pw",
                panel="panel-one",
                traffic_gb=10.0,
                expiry_days=None,
                telegram_id=None,
            )
        )

    assert admin_row("bad name") is None


def test_create_admin_for_shop_refuses_a_username_with_a_space(
    marzban_never_contacted, panel_client, admin_row
):
    with pytest.raises(panel_client.PanelClientError, match="English letters"):
        asyncio.run(
            panel_client.create_admin_for_shop(
                username="bad name",
                password="pw",
                panel="panel-one",
                traffic_gb=10.0,
                telegram_id=111,
            )
        )

    assert admin_row("bad name") is None


def test_create_panel_refuses_a_sudo_username_with_a_space(
    marzban_never_contacted, panel_client
):
    with pytest.raises(panel_client.PanelClientError, match="spaces"):
        asyncio.run(
            panel_client.create_panel(
                name="new-panel",
                url="http://marzban.test:8000",
                username="sudo user",
                password="pw",
            )
        )


def test_bot_http_endpoint_rejects_a_username_with_a_space():
    """The endpoint's payload is validated before anything is provisioned."""
    with pytest.raises(ValidationError):
        BotCreateAdminInput(
            username="bad name", password="pw", panel="panel-one", traffic_gb=15.0
        )


# ── one rule shared with the MIT Panel login form ──────────────────────────
# frontend/src/types/index.ts → USERNAME_REGEX, 3–50 characters. A panel the
# bot creates under any other name could never be logged into.

@pytest.mark.parametrize(
    "value",
    ["reseller_1", "a.b-c", "abc", "Ali99", "9lives", "a" * 50],
)
def test_valid_usernames_are_accepted(value):
    assert validation.is_valid_username(value) is True


@pytest.mark.parametrize(
    "value",
    [
        "ali@shop",          # the reported bug
        "@ali",
        "ab",                # too short
        "a" * 51,            # too long
        "",
        "_ali",              # must start with a letter or digit
        ".ali",
        "-ali",
        "ali\n",             # `$` would let a trailing newline through
        "ali name",
        "ali​",         # zero-width space
        "аli",          # Cyrillic а
        "۱۲۳abc",            # Persian digits
        "علی123",
        "<b>x</b>",
        "ali/../x",
        "ali#1",
        "ali+1",
        "ali:1",
        "ali%20",
    ],
)
def test_unusual_usernames_are_refused(value):
    assert validation.is_valid_username(value) is False


@pytest.mark.parametrize(
    "value,expected",
    [
        ("abc12345", True),
        ("Abc!@#45", True),
        ("x1" * 50, True),           # exactly 100
        ("x1" * 50 + "y", False),    # 101 — the login form stops at 100
        ("abc1234", False),          # 7 characters
        ("abcdefgh", False),         # no digit
        ("12345678", False),         # no letter
        ("abc 12345", False),        # space
        ("abc12345\t", False),
        ("abcd۱۲۳۴", False),         # Persian digits are not digits here
        ("رمزعبور12", False),        # Persian letters
        ("abc​12345", False),   # zero-width space
    ],
)
def test_password_rule(value, expected):
    assert validation.is_strong_password(value) is expected


def test_shop_username_with_an_at_sign_is_refused(monkeypatch):
    message, state = _pair("ali@shop")
    lookup = AsyncMock(return_value=False)
    monkeypatch.setattr(panel_client, "check_username_taken", lookup)

    asyncio.run(shop.shop_get_username(message, state))

    assert message.answer.await_args.args[0] == texts.USERNAME_INVALID
    lookup.assert_not_awaited()
    state.update_data.assert_not_awaited()
    state.set_state.assert_not_awaited()


def test_create_admin_username_with_an_at_sign_is_refused(monkeypatch):
    message, state = _pair("ali@shop")
    lookup = AsyncMock(return_value=False)
    monkeypatch.setattr(panel_client, "check_username_taken", lookup)

    asyncio.run(admin_settings.create_admin_username(message, state))

    assert message.answer.await_args.args[0] == texts.USERNAME_INVALID
    lookup.assert_not_awaited()
    state.update_data.assert_not_awaited()


def test_superadmin_bot_password_uses_the_shared_rule():
    message, state = _pair("abcd۱۲۳۴")

    asyncio.run(admin_settings.create_admin_password(message, state))

    assert message.answer.await_args.args[0] == texts.SHOP_PASSWORD_WEAK
    state.update_data.assert_not_awaited()


def test_create_admin_for_shop_refuses_an_at_sign(
    marzban_never_contacted, panel_client, admin_row
):
    with pytest.raises(panel_client.PanelClientError, match="English letters"):
        asyncio.run(
            panel_client.create_admin_for_shop(
                username="ali@shop",
                password="abc12345",
                panel="panel-one",
                traffic_gb=10.0,
                telegram_id=111,
            )
        )

    assert admin_row("ali@shop") is None


def test_schemas_refuse_an_at_sign():
    from backend.schema._input import AdminInput

    with pytest.raises(ValidationError):
        BotCreateAdminInput(
            username="ali@shop", password="pw", panel="panel-one", traffic_gb=15.0
        )
    with pytest.raises(ValidationError):
        AdminInput(
            username="ali@shop", password="pw", panel="panel-one", expiry_date=None
        )
    # The login form's own rule still passes, upper case included.
    assert AdminInput(
        username="Reseller_1", password="pw", panel="panel-one", expiry_date=None
    ).username == "Reseller_1"


def test_admin_update_input_keeps_accepting_existing_names():
    """Editing a panel created before this rule must keep working."""
    from backend.schema._input import AdminUpdateInput

    AdminUpdateInput(
        username="old@name", is_active=True, panel="panel-one",
        traffic=0, expiry_date=None,
    )


def test_duplicate_check_ignores_case(db_session, panel_client):
    from backend.db import crud
    from backend.db.model import Admins

    db_session.add(Admins(username="Reseller", hashed_password="x", panel="panel-one"))
    db_session.commit()

    assert crud.admin_username_exists(db_session, "reseller") is True
    assert crud.admin_username_exists(db_session, "RESELLER") is True
    assert crud.admin_username_exists(db_session, "other") is False
    assert asyncio.run(panel_client.check_username_taken("reseller")) is True
