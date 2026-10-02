"""The nightly digest: one message per day, at the configured Tehran hour,
and never twice for the same day however often the process restarts.

`uv run pytest` picks up the interpreter on PATH, which has no aiogram — so
these run the coroutines with `asyncio.run` instead of needing an async plugin.
"""

import asyncio
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from backend.bot import digest
from backend.bot.config import bot_config

TEHRAN = ZoneInfo("Asia/Tehran")


@pytest.fixture()
def clock(monkeypatch):
    """Pin `digest`'s idea of now and of the hour the digest goes out."""
    monkeypatch.setattr(type(bot_config), "digest_hour", property(lambda self: 22))
    monkeypatch.setattr(
        type(bot_config), "superadmin_id_list", property(lambda self: [1, 2])
    )

    def set_now(year, month, day, hour, minute=0):
        fixed = datetime(year, month, day, hour, minute, tzinfo=TEHRAN)

        class _Clock:
            @staticmethod
            def now(tz=None):
                return fixed

        monkeypatch.setattr(digest, "datetime", _Clock)

    return set_now


class _RecordingBot:
    def __init__(self, fail_for: int | None = None):
        self.sent: list[tuple[int, str]] = []
        self._fail_for = fail_for

    async def send_message(self, chat_id: int, text: str) -> None:
        if chat_id == self._fail_for:
            raise RuntimeError("blocked the bot")
        self.sent.append((chat_id, text))


def test_build_reports_a_quiet_day(ledger, clock):
    clock(2026, 10, 2, 12)

    text = asyncio.run(digest.build())

    assert text.startswith(digest.texts.DIGEST_HEADER.split("{day}")[0])
    assert digest.texts.DIGEST_NO_SALES in text
    assert digest.texts.DIGEST_NO_PENDING in text
    assert digest.texts.DIGEST_NO_OVERDUE in text
    assert digest.texts.DIGEST_NO_LOW_PANELS in text


def test_tick_sends_once_per_day(ledger, clock):
    clock(2026, 10, 2, 22, 5)
    bot = _RecordingBot()

    assert asyncio.run(digest.tick(bot)) is True
    assert [chat_id for chat_id, _ in bot.sent] == [1, 2]

    # Same evening, or a restart inside the same hour: stamped already.
    assert asyncio.run(digest.tick(bot)) is False
    assert len(bot.sent) == 2

    clock(2026, 10, 3, 22, 5)
    assert asyncio.run(digest.tick(bot)) is True
    assert len(bot.sent) == 4


def test_tick_stays_quiet_outside_the_configured_hour(ledger, clock):
    clock(2026, 10, 2, 9)
    bot = _RecordingBot()

    assert asyncio.run(digest.tick(bot)) is False
    assert bot.sent == []


def test_one_unreachable_superadmin_does_not_stop_the_others(ledger, clock):
    clock(2026, 10, 2, 22)
    bot = _RecordingBot(fail_for=1)

    assert asyncio.run(digest.tick(bot)) is True
    assert [chat_id for chat_id, _ in bot.sent] == [2]
