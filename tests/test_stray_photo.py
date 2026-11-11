"""Receipts that arrive outside any flow get an answer, not silence.

A photo that matched no handler used to vanish: the customer believed their
receipt was delivered while the superadmin waited for a request that did not
exist (production, 2026-11-11, user id 1131519306). The fallback router now
tells the sender how to get the receipt into a real flow.
"""

import asyncio
from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot import texts
from backend.bot.routers import photo_fallback
from backend.bot.states import TopUp

CUSTOMER = 1131519306
SUPERADMIN = 1451599691


class FakeMessage:
    def __init__(self, user_id: int):
        self.from_user = SimpleNamespace(id=user_id, username="someone")
        self.photo = [SimpleNamespace(file_id="photo-file-id")]
        self.answers: list[str] = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append(text)
        return self


def _state() -> FSMContext:
    return FSMContext(storage=MemoryStorage(), key=StorageKey(chat_id=1, user_id=1, bot_id=1))


def test_a_stateless_receipt_photo_is_answered_with_guidance(ledger, monkeypatch):
    monkeypatch.setattr(photo_fallback, "settings", SimpleNamespace(superadmin_id_list=[SUPERADMIN]))
    message = FakeMessage(CUSTOMER)

    asyncio.run(photo_fallback.stray_photo(message, _state()))

    assert message.answers == [texts.STRAY_PHOTO_GUIDANCE]


def test_a_photo_in_a_text_step_is_told_the_step_takes_text(ledger, monkeypatch):
    monkeypatch.setattr(photo_fallback, "settings", SimpleNamespace(superadmin_id_list=[SUPERADMIN]))

    async def scenario() -> FakeMessage:
        state = _state()
        await state.set_state(TopUp.amount_gb)
        message = FakeMessage(CUSTOMER)
        await photo_fallback.stray_photo(message, state)
        return message

    assert asyncio.run(scenario()).answers == [texts.STRAY_PHOTO_MISPLACED]


def test_superadmins_are_left_alone(ledger, monkeypatch):
    monkeypatch.setattr(photo_fallback, "settings", SimpleNamespace(superadmin_id_list=[SUPERADMIN]))
    message = FakeMessage(SUPERADMIN)

    asyncio.run(photo_fallback.stray_photo(message, _state()))

    assert message.answers == []
