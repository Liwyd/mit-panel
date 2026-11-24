"""/start, the force-join gate and the Black Friday welcome.

- A first /start the force-join gate stops still reaches the superadmins at
  once, and only once.
- «✅ عضو شدم» lands the user in the bot; it no longer asks them to /start again.
- While Black Friday runs, /start adds a countdown and the offer — no price.
"""

import asyncio
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

import backend.bot.panel_client as panel_client_module
from backend.bot import black_friday, middlewares, nav, texts
from backend.bot.routers import start

SUPER = 9000000001
NEWBIE = 7000000123


class FakeBot:
    def __init__(self, member_status="left"):
        self.sent: list[tuple[int, str]] = []
        self.member_status = member_status

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))

    async def get_chat_member(self, channel, user_id):
        return SimpleNamespace(status=self.member_status)


def _user(user_id=NEWBIE):
    return SimpleNamespace(id=user_id, username="newbie", full_name="New <Bie>")


class FakeMessage:
    def __init__(self, user, text="/start"):
        self.from_user = user
        self.text = text
        self.answers: list[str] = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append(text)

    async def delete(self):
        pass


class FakeState:
    async def clear(self):
        pass


@pytest.fixture()
def bot_env(db_session, ledger, monkeypatch):
    fake_settings = SimpleNamespace(superadmin_id_list=[SUPER])
    for module in (start, middlewares, nav):
        monkeypatch.setattr(module, "settings", fake_settings)

    async def no_panels(telegram_id):
        return []

    monkeypatch.setattr(panel_client_module, "get_admins", no_panels)
    monkeypatch.setattr(black_friday, "time_left_text", lambda now=None: None)
    return ledger


def _gate_on(ledger):
    ledger.set_setting("force_join_enabled", "1")
    ledger.set_setting("force_join_channel", "@mitchannel")


def _through_gate(bot, message, handler):
    data = {"event_from_user": message.from_user, "bot": bot}
    return asyncio.run(middlewares.ForceJoinMiddleware()(handler, message, data))


def _super_messages(bot):
    return [text for chat, text in bot.sent if chat == SUPER]


# ── the superadmin hears about a new user before they join ──────────────────

def test_a_blocked_first_start_still_notifies_the_superadmin(bot_env):
    _gate_on(bot_env)
    bot = FakeBot(member_status="left")
    called = []

    async def handler(event, data):
        called.append(event)

    _through_gate(bot, FakeMessage(_user()), handler)

    assert called == []  # still gated
    assert (NEWBIE, texts.FORCE_JOIN_TEXT) in bot.sent
    [notice] = _super_messages(bot)
    assert str(NEWBIE) in notice
    assert texts.NEW_START_NOT_JOINED_YET in notice
    assert "New &lt;Bie&gt;" in notice  # names are escaped for HTML
    assert bot_env.user_exists(NEWBIE)


def test_the_superadmin_is_told_only_once(bot_env):
    _gate_on(bot_env)
    bot = FakeBot(member_status="left")

    async def handler(event, data):
        pass

    _through_gate(bot, FakeMessage(_user()), handler)
    _through_gate(bot, FakeMessage(_user()), handler)  # a second blocked /start

    # They join, then /start runs for real.
    asyncio.run(start.start(FakeMessage(_user()), bot))

    assert len(_super_messages(bot)) == 1


def test_other_blocked_messages_do_not_notify(bot_env):
    _gate_on(bot_env)
    bot = FakeBot(member_status="left")

    async def handler(event, data):
        pass

    _through_gate(bot, FakeMessage(_user(), text="hello"), handler)

    assert _super_messages(bot) == []
    assert not bot_env.user_exists(NEWBIE)


def test_an_unblocked_first_start_notifies_once(bot_env):
    bot = FakeBot()
    message = FakeMessage(_user())

    asyncio.run(start.start(message, bot))

    assert len(_super_messages(bot)) == 1
    assert texts.NEW_START_NOT_JOINED_YET not in _super_messages(bot)[0]
    assert message.answers == [texts.START_UNLINKED]


# ── «✅ عضو شدم» goes straight in ────────────────────────────────────────────

def test_joined_button_shows_the_welcome_instead_of_asking_for_start(bot_env):
    bot = FakeBot(member_status="member")
    message = FakeMessage(_user())
    toasts = []

    async def answer(text=None, **kwargs):
        toasts.append(text)

    call = SimpleNamespace(from_user=_user(), message=message, answer=answer)

    asyncio.run(start.recheck_join(call, bot, FakeState()))

    assert toasts == [texts.FORCE_JOIN_CONFIRMED]
    assert "/start" not in texts.FORCE_JOIN_CONFIRMED
    assert message.answers == [texts.START_UNLINKED]


# ── Black Friday on /start ──────────────────────────────────────────────────

def test_black_friday_start_message_has_the_countdown_and_no_price(bot_env, monkeypatch):
    monkeypatch.setattr(black_friday, "time_left_text", lambda now=None: "3 روز و 5 ساعت")
    monkeypatch.setattr(black_friday, "gift_eligible", lambda username: True)
    message = FakeMessage(_user())

    asyncio.run(start.start(message, FakeBot()))

    assert message.answers[0] == texts.START_UNLINKED
    promo = message.answers[1]
    assert "3 روز و 5 ساعت" in promo
    assert "تخفیف" in promo and "هدیه" in promo
    assert "تومان" not in promo
    assert not any(ch.isdigit() for ch in promo.replace("3 روز و 5 ساعت", ""))


def test_no_gift_promised_when_new_panels_get_none(bot_env, monkeypatch):
    monkeypatch.setattr(black_friday, "time_left_text", lambda now=None: "2 روز")
    monkeypatch.setattr(black_friday, "gift_eligible", lambda username: False)
    message = FakeMessage(_user())

    asyncio.run(start.start(message, FakeBot()))

    assert texts.BF_START_OFFER_PLAIN in message.answers[1]
    assert "هدیه" not in message.answers[1]


def test_no_black_friday_message_outside_the_event(bot_env):
    message = FakeMessage(_user())

    asyncio.run(start.start(message, FakeBot()))

    assert message.answers == [texts.START_UNLINKED]


def _ends_in(monkeypatch, delta):
    end = datetime(2026, 11, 28, 23, 59, tzinfo=timezone.utc)
    monkeypatch.setattr(
        "backend.utils.settings_store.black_friday_state",
        lambda: {"active": True, "ends_at": end.isoformat()},
    )
    return end - delta


@pytest.mark.parametrize(
    "delta,expected",
    [
        (timedelta(days=3, hours=5, minutes=10), "3 روز و 5 ساعت"),
        (timedelta(days=2, minutes=30), "2 روز"),
        (timedelta(hours=7, minutes=59), "7 ساعت"),
        (timedelta(minutes=12), texts.BF_TIME_LEFT_UNDER_HOUR),
    ],
)
def test_time_left_text(monkeypatch, delta, expected):
    now = _ends_in(monkeypatch, delta)
    assert black_friday.time_left_text(now) == expected


def test_time_left_is_none_when_inactive_or_over(monkeypatch):
    monkeypatch.setattr(
        "backend.utils.settings_store.black_friday_state",
        lambda: {"active": False, "ends_at": None},
    )
    assert black_friday.time_left_text() is None

    now = _ends_in(monkeypatch, timedelta(seconds=-5))
    assert black_friday.time_left_text(now) is None
