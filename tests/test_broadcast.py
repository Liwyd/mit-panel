"""Superadmin broadcast: any message type, preview, audiences, pacing."""

import asyncio
from types import SimpleNamespace

import pytest
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot import broadcast, texts
from backend.bot.routers import broadcast as bc_router
from backend.bot.states import Broadcast

OWNER = 1451599691


class FakeBot:
    def __init__(self, errors=None):
        self.calls = []
        self.errors = errors or {}  # chat_id -> list of exceptions to raise (popped)

    async def _do(self, kind, chat_id, from_chat_id, message_ids):
        queue = self.errors.get(chat_id)
        if queue:
            exc = queue.pop(0)
            if exc is not None:
                raise exc
        self.calls.append((kind, chat_id, from_chat_id, list(message_ids)))

    async def copy_messages(self, chat_id, from_chat_id, message_ids):
        await self._do("copy", chat_id, from_chat_id, message_ids)

    async def forward_messages(self, chat_id, from_chat_id, message_ids):
        await self._do("forward", chat_id, from_chat_id, message_ids)

    async def send_message(self, chat_id, text, **kw):
        self.calls.append(("text", chat_id, text))


class FakeMessage:
    def __init__(self, mid, text=None, group=None, forwarded=False):
        self.message_id = mid
        self.text = text
        self.media_group_id = group
        self.forward_origin = object() if forwarded else None
        self.from_user = SimpleNamespace(id=OWNER)
        self.answers = []

    async def answer(self, text, reply_markup=None, **kw):
        self.answers.append((text, reply_markup))


class FakeCall:
    def __init__(self, data):
        self.data = data
        self.from_user = SimpleNamespace(id=OWNER)
        self.message = FakeMessage(0)
        self.alerts = []

    async def answer(self, text=None, show_alert=False, **kw):
        if text:
            self.alerts.append(text)


def _state():
    return FSMContext(storage=MemoryStorage(), key=StorageKey(chat_id=1, user_id=1, bot_id=1))


@pytest.fixture(autouse=True)
def _fast(monkeypatch):
    monkeypatch.setattr(broadcast, "PACE_SECONDS", 0)
    monkeypatch.setattr(broadcast.db, "list_known_users", lambda: [OWNER, 1, 2, 3])
    monkeypatch.setattr(broadcast.db, "list_linked_users", lambda: [OWNER, 2])
    broadcast.release()
    yield
    broadcast.release()


async def _collect(state, *messages):
    await state.set_state(Broadcast.collect)
    for m in messages:
        await bc_router.collect_message(m, state)


def _drain():
    async def go():
        while broadcast._tasks:
            await asyncio.gather(*list(broadcast._tasks))

    return go()


def test_photo_without_text_is_queued():
    async def go():
        state = _state()
        m = FakeMessage(10)
        await _collect(state, m)
        return (await state.get_data())["draft"], m.answers

    draft, answers = asyncio.run(go())
    assert draft == [{"id": 10, "forwarded": False, "group": None}]
    assert answers[0][0] == texts.BROADCAST_QUEUED.format(count=1)


def test_album_is_three_ids_with_one_ack():
    async def go():
        state = _state()
        ms = [FakeMessage(i, group="g") for i in (1, 2, 3)]
        await _collect(state, *ms)
        return [d["id"] for d in (await state.get_data())["draft"]], sum(len(m.answers) for m in ms)

    ids, acks = asyncio.run(go())
    assert ids == [1, 2, 3] and acks == 1


def test_menu_button_text_is_not_queued():
    # The handler's filter is what excludes menu texts.
    from aiogram import F
    from backend.bot.nav import ALL_MENU_TEXTS

    assert texts.BTN_BROADCAST in ALL_MENU_TEXTS and texts.BTN_CANCEL in ALL_MENU_TEXTS
    flt = (~F.text.in_(ALL_MENU_TEXTS))
    assert flt.resolve(SimpleNamespace(text=texts.BTN_CANCEL)) is False
    assert flt.resolve(SimpleNamespace(text="hello")) is True
    assert flt.resolve(SimpleNamespace(text=None)) is True


def test_cap_at_50():
    async def go():
        state = _state()
        ms = [FakeMessage(i) for i in range(52)]
        await _collect(state, *ms)
        return len((await state.get_data())["draft"]), ms[51].answers

    n, answers = asyncio.run(go())
    assert n == 50 and answers[0][0] == texts.BROADCAST_QUEUE_FULL.format(limit=50)


def test_forward_and_copy_runs_in_order():
    draft = [
        {"id": 1, "forwarded": True, "group": None},
        {"id": 2, "forwarded": True, "group": None},
        {"id": 3, "forwarded": False, "group": None},
        {"id": 4, "forwarded": True, "group": None},
    ]
    bot = FakeBot()
    asyncio.run(broadcast.send_draft(bot, 7, OWNER, draft))
    assert bot.calls == [
        ("forward", 7, OWNER, [1, 2]),
        ("copy", 7, OWNER, [3]),
        ("forward", 7, OWNER, [4]),
    ]


def test_more_than_100_ids_are_chunked():
    draft = [{"id": i, "forwarded": False, "group": None} for i in range(250)]
    bot = FakeBot()
    asyncio.run(broadcast.send_draft(bot, 7, OWNER, draft))
    assert [len(c[3]) for c in bot.calls] == [100, 100, 50]


def test_preview_goes_to_superadmin_and_shows_counts():
    async def go():
        state, bot, call = _state(), FakeBot(), FakeCall("bc:preview")
        await _collect(state, FakeMessage(5))
        await bc_router.preview(call, state, bot)
        return bot.calls, call.message.answers

    calls, answers = asyncio.run(go())
    assert calls == [("copy", OWNER, OWNER, [5])]
    buttons = [b.text for row in answers[-1][1].inline_keyboard for b in row]
    assert buttons[0] == texts.BTN_BROADCAST_ALL.format(count=4)
    assert buttons[1] == texts.BTN_BROADCAST_LINKED.format(count=2)


def test_empty_preview():
    async def go():
        state, bot, call = _state(), FakeBot(), FakeCall("bc:preview")
        await state.set_state(Broadcast.collect)
        await bc_router.preview(call, state, bot)
        return bot.calls, call.message.answers

    calls, answers = asyncio.run(go())
    assert calls == [] and answers[0][0] == texts.BROADCAST_QUEUE_EMPTY


def _send(kind, bot, state):
    async def go():
        call = FakeCall(f"bc:send:{kind}")
        await bc_router.send(call, state, bot)
        await _drain()
        return call

    return go()


def test_send_all_vs_linked_skips_owner_and_reports():
    async def go(kind):
        state, bot = _state(), FakeBot()
        await _collect(state, FakeMessage(5))
        await _send(kind, bot, state)
        return bot

    all_bot = asyncio.run(go("all"))
    linked_bot = asyncio.run(go("linked"))
    assert [c[1] for c in all_bot.calls if c[0] == "copy"] == [1, 2, 3]
    assert [c[1] for c in linked_bot.calls if c[0] == "copy"] == [2]
    assert all_bot.calls[-1][0] == "text" and all_bot.calls[-1][1] == OWNER
    assert "3" in all_bot.calls[-1][2]


def test_retry_after_is_retried_then_succeeds():
    retry = TelegramRetryAfter(method=None, message="x", retry_after=0)
    bot = FakeBot({7: [retry, retry]})
    asyncio.run(broadcast.send_draft(bot, 7, OWNER, [{"id": 1, "forwarded": False, "group": None}]))
    assert bot.calls == [("copy", 7, OWNER, [1])]


def test_forbidden_counted_as_blocked_and_other_errors_failed():
    async def go():
        state = _state()
        bot = FakeBot({
            1: [TelegramForbiddenError(method=None, message="blocked")],
            2: [RuntimeError("boom")],
        })
        await _collect(state, FakeMessage(5))
        await _send("all", bot, state)
        return bot.calls[-1][2]

    report = asyncio.run(go())
    assert texts.BROADCAST_RESULT.split("{")[0] in report
    assert "مسدود کرده‌اند: 1" in report and "ناموفق: 1" in report and "موفق: 1" in report


def test_double_confirm_starts_one_broadcast():
    async def go():
        state, bot = _state(), FakeBot()
        await _collect(state, FakeMessage(5))
        c1, c2 = FakeCall("bc:send:all"), FakeCall("bc:send:all")
        await bc_router.send(c1, state, bot)
        await bc_router.send(c2, state, bot)
        await _drain()
        return bot, c2

    bot, c2 = asyncio.run(go())
    assert sum(1 for c in bot.calls if c[0] == "text") == 1
    assert len([c for c in bot.calls if c[0] == "copy"]) == 3


def test_second_broadcast_refused_while_running():
    async def go():
        state, bot = _state(), FakeBot()
        await _collect(state, FakeMessage(5))
        assert broadcast.try_acquire()
        call = FakeCall("bc:send:all")
        await bc_router.send(call, state, bot)
        return bot, call, (await state.get_data())["draft"]

    bot, call, draft = asyncio.run(go())
    assert call.alerts == [texts.BROADCAST_BUSY] and bot.calls == [] and draft


def test_cancel_and_clear():
    async def go():
        state = _state()
        await _collect(state, FakeMessage(5))
        await bc_router.clear_queue(FakeCall("bc:clear"), state)
        cleared = (await state.get_data())["draft"]
        await bc_router.cancel(FakeCall("bc:cancel"), state)
        return cleared, await state.get_state(), await state.get_data()

    cleared, st, data = asyncio.run(go())
    assert cleared == [] and st is None and data == {}
