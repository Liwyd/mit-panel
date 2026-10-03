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

    assert message.answer.await_args.args[0] == texts.USERNAME_NO_SPACE
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

    assert message.answer.await_args.args[0] == texts.USERNAME_NO_SPACE
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
    with pytest.raises(panel_client.PanelClientError, match="spaces"):
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
    with pytest.raises(panel_client.PanelClientError, match="spaces"):
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
