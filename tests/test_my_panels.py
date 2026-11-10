"""«پنل‌های من» points at their panels the way every panel-delivery flow does.

When the shop approves a request, or the superadmin builds a panel, the
credentials arrive with the same two login links attached («ورود به پنل با
VPN», «ورود به پنل بدون VPN» from the panel's settings). A sub-admin tapping
«پنل‌های من» used to get the panels list with no route to it at all, so this
list carries the same buttons under it — same labels, same URLs, read from the
same place.
"""

import asyncio
from types import SimpleNamespace

import backend.bot.panel_client as panel_client_module
from backend.bot import keyboards, texts
from backend.bot.routers import start

VIEWER = 7000000001


class FakeMessage:
    def __init__(self, user_id: int) -> None:
        self.from_user = SimpleNamespace(id=user_id, full_name="Reseller")
        self.text = texts.BTN_MY_PANELS
        self.answers: list[tuple[str, object]] = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append((text, reply_markup))


def _run(coroutine):
    return asyncio.run(coroutine)


def _panel(username: str) -> dict:
    return {
        "username": username,
        "telegram_id": VIEWER,
        "traffic": 1000,
        "initial_traffic": 2000,
        "is_active": True,
        "panel": "panel-one",
        "marzban_password": "reseller-pass",
    }


def _login_urls(monkeypatch):
    monkeypatch.setattr(
        "backend.utils.settings_store.get_settings",
        lambda: {
            "bot_panel_login_vpn_url": "https://vpn.example/panpan",
            "bot_panel_login_direct_url": "https://direct.example/panpan",
        },
    )


def test_my_panels_carries_the_login_links(db_session, ledger, monkeypatch):
    panels = [_panel("seller")]

    async def fake_get_admins(telegram_id):
        return panels

    monkeypatch.setattr(panel_client_module, "get_admins", fake_get_admins)
    _login_urls(monkeypatch)

    message = FakeMessage(VIEWER)
    _run(start.my_panels(message))

    [answer] = message.answers
    body, markup = answer
    assert "seller" in body
    labels = [btn.text for rows in markup.inline_keyboard for btn in rows]
    urls = [getattr(btn, "url", None) for rows in markup.inline_keyboard for btn in rows]
    # The history buttons come first, one per panel, unchanged.
    assert labels[0] == f"{texts.BTN_HISTORY} · seller"
    # And the same two login links close the list.
    assert labels[1:] == [texts.BTN_PANEL_LOGIN_VPN, texts.BTN_PANEL_LOGIN_DIRECT]
    assert urls[-2:] == ["https://vpn.example/panpan", "https://direct.example/panpan"]


def test_the_panel_delivery_keyboard_offers_the_two_links(monkeypatch):
    """Regression for the flows that already sent the buttons: same shape."""
    _login_urls(monkeypatch)

    markup = keyboards.panel_login_kb()

    assert [(btn.text, btn.url) for rows in markup.inline_keyboard for btn in rows] == [
        (texts.BTN_PANEL_LOGIN_VPN, "https://vpn.example/panpan"),
        (texts.BTN_PANEL_LOGIN_DIRECT, "https://direct.example/panpan"),
    ]
