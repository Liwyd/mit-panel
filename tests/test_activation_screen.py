"""The activation screen is the first thing a stranger sees, so it offers the
shop and nothing else — the cooperation form is gone.

Its label is kept in `ALL_MENU_TEXTS` on purpose: Telegram leaves the old
reply keyboard on screen until a new one replaces it, and a label that the
navigation map doesn't know about gets swallowed as free text by whatever FSM
handler is waiting."""

from backend.bot import keyboards, nav, routers, texts


def test_the_activation_screen_only_offers_the_shop():
    labels = [
        button.text for row in keyboards.panel_request_kb().keyboard for button in row
    ]

    assert labels == [texts.BTN_REQUEST_PANEL, texts.BTN_BACK]


def test_the_cooperation_router_is_gone():
    assert [r.name for r in routers.all_routers if "partnership" in r.name] == []


def test_the_retired_cooperation_label_is_still_a_known_menu_label():
    assert texts.BTN_PARTNERSHIP in nav.ALL_MENU_TEXTS
