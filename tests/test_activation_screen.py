"""The activation screen is the first thing a user with no panel sees, so both
ways of asking for one have to be on it — otherwise the cooperation form is
something only the menu can reach."""

from backend.bot import keyboards, nav, texts


def test_the_activation_screen_offers_the_cooperation_form():
    labels = [
        button.text for row in keyboards.panel_request_kb().keyboard for button in row
    ]

    assert labels == [texts.BTN_PARTNERSHIP, texts.BTN_REQUEST_PANEL, texts.BTN_BACK]
    # And it is a reply-keyboard label the menu scanner already knows about.
    assert texts.BTN_PARTNERSHIP in nav.ALL_MENU_TEXTS
