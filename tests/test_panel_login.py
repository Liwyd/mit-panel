from backend.bot import keyboards, texts
from backend.utils.settings_store import DEFAULTS


def test_login_buttons(monkeypatch):
    monkeypatch.setattr('backend.utils.settings_store.get_settings', lambda: dict(DEFAULTS))
    buttons = [b for row in keyboards.panel_login_kb().inline_keyboard for b in row]
    assert [(b.text, b.url) for b in buttons] == [
        ('ورود به پنل با VPN', 'https://dwunli.draking.ir:4000/panpan/'),
        ('ورود به پنل بدون VPN', 'https://wunli.draking.ir:4000/panpan/'),
    ]
    assert DEFAULTS['bot_panel_link_url'] == 'https://dwunli.draking.ir:4000/panpan/'
    for template in (texts.CREATE_ADMIN_SUCCESS, texts.SHOP_REQUEST_APPROVED, texts.PANEL_LINK_INFO):
        assert '{url}' not in template
