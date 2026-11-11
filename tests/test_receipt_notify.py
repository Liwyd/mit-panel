"""Delivery of a pending receipt to the superadmins.

The notification is the only way a pending request becomes reviewable, so it
is retried, logged and never allowed to raise — a request that was stored but
never announced is a customer waiting for nothing.
"""

import asyncio
import logging
from types import SimpleNamespace

import pytest

from backend.bot import notify

SUPERADMIN = 1451599691
OTHER_SUPERADMIN = 6900787101


class FakeBot:
    def __init__(self, fail_ids=(), fail_once_ids=()):
        self.sent = []
        self._fail_ids = set(fail_ids)
        self._fail_once_ids = set(fail_once_ids)

    async def send_photo(self, chat_id, photo=None, caption=None, reply_markup=None, **kwargs):
        chat_id = int(chat_id)
        if chat_id in self._fail_ids:
            raise RuntimeError("telegram down")
        if chat_id in self._fail_once_ids:
            self._fail_once_ids.discard(chat_id)
            raise RuntimeError("blip")
        self.sent.append(chat_id)


@pytest.fixture(autouse=True)
def _fast_retries(monkeypatch):
    monkeypatch.setattr(notify, "_RETRY_DELAY_SECONDS", 0)


@pytest.fixture()
def bot_for(monkeypatch):
    def _wire(bot, superadmins=(SUPERADMIN, OTHER_SUPERADMIN)):
        monkeypatch.setattr(
            notify, "settings", SimpleNamespace(superadmin_id_list=list(superadmins))
        )
        return bot

    return _wire


def _send(bot):
    return asyncio.run(
        notify.send_receipt_to_superadmins(
            bot,
            photo="photo-file-id",
            caption="🧾 رسید #1",
            reply_markup=None,
            request_id=1,
            kind="panel",
        )
    )


def test_a_receipt_reaches_every_superadmin(bot_for):
    bot = bot_for(FakeBot())
    assert _send(bot) == 2
    assert bot.sent == [SUPERADMIN, OTHER_SUPERADMIN]


def test_a_transient_failure_is_retried_and_still_delivered(bot_for):
    bot = bot_for(FakeBot(fail_once_ids={OTHER_SUPERADMIN}))
    assert _send(bot) == 2
    assert bot.sent == [SUPERADMIN, OTHER_SUPERADMIN]


def test_a_dead_superadmin_does_not_block_the_others(bot_for):
    bot = bot_for(FakeBot(fail_ids={SUPERADMIN}))
    assert _send(bot) == 1
    assert bot.sent == [OTHER_SUPERADMIN]


def test_when_nobody_gets_it_the_request_is_named_in_the_log(bot_for, caplog):
    bot = bot_for(FakeBot(fail_ids={SUPERADMIN, OTHER_SUPERADMIN}))
    with caplog.at_level(logging.CRITICAL, logger="backend.bot.notify"):
        assert _send(bot) == 0
    assert bot.sent == []
    assert any("#1" in record.message and "panel" in record.message for record in caplog.records)


def test_no_configured_superadmin_is_a_logged_error_not_a_crash(bot_for, caplog):
    bot = bot_for(FakeBot(), superadmins=())
    with caplog.at_level(logging.ERROR, logger="backend.bot.notify"):
        assert _send(bot) == 0
    assert bot.sent == []
    assert any("no superadmin" in record.message for record in caplog.records)
