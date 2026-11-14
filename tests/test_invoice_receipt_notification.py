"""A paid invoice's receipt must tell the superadmin who paid and for what.

The caption used to carry only the payer's numeric ID, so the reviewer had to
dig the invoice up to learn which sub-admin panel the money settles. It now
names the panel the invoice bills and the payer's @username — and because the
caption is built after the request is already stored, every lookup degrades on
its own instead of eating the notification the way the shop crash once did.
"""

import asyncio
from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot import db as bot_db
from backend.bot import notify
from backend.bot.routers import wallet
from backend.bot.states import InvoicePayment

CUSTOMER = 79703710
SUPERADMIN = 1451599691
PANEL = "kara"
AMOUNT = 1_150_000


class FakePhoto:
    file_id = "photo-file-id"


class FakeMessage:
    def __init__(self, user_id: int, username: str | None):
        self.from_user = SimpleNamespace(id=user_id, username=username)
        self.photo = [FakePhoto()]
        self.answers: list[str] = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append(text)
        return self


class FakeBot:
    def __init__(self):
        self.photos = []

    async def download(self, photo, destination):
        with open(destination, "wb") as fh:
            fh.write(b"receipt")
        return destination

    async def send_photo(self, chat_id, photo=None, caption=None, reply_markup=None, **kwargs):
        self.photos.append({"chat_id": int(chat_id), "caption": caption})


def _run_invoice_flow(monkeypatch, tmp_path, username: str | None = "matin_test") -> FakeBot:
    monkeypatch.setattr(
        wallet,
        "settings",
        SimpleNamespace(superadmin_id_list=[SUPERADMIN], media_dir=str(tmp_path / "media")),
    )
    monkeypatch.setattr(notify, "settings", SimpleNamespace(superadmin_id_list=[SUPERADMIN]))
    message = FakeMessage(CUSTOMER, username)
    bot = FakeBot()
    invoice_id = bot_db.create_invoice(
        telegram_id=CUSTOMER,
        amount=AMOUNT,
        description="weekly usage",
        due_at=None,
        admin_username=PANEL,
    )

    async def scenario():
        state = FSMContext(
            storage=MemoryStorage(),
            key=StorageKey(chat_id=1, user_id=1, bot_id=1),
        )
        await state.set_state(InvoicePayment.receipt)
        await state.update_data(invoice_id=invoice_id, invoice_amount=AMOUNT)
        await wallet.get_invoice_receipt(message, state, bot)

    asyncio.run(scenario())
    return bot


def test_the_caption_names_the_panel_and_the_payer(ledger, monkeypatch, tmp_path):
    bot = _run_invoice_flow(monkeypatch, tmp_path)

    assert bot.photos, "the superadmin was never notified"
    assert bot.photos[0]["chat_id"] == SUPERADMIN
    caption = bot.photos[0]["caption"]
    assert f"👤 آیدی عددی: {CUSTOMER} (@matin_test) — برای پنل {PANEL}" in caption
    assert f"💰 مبلغ: {AMOUNT:,} تومان" in caption


def test_a_payer_without_a_telegram_username_is_still_identified(ledger, monkeypatch, tmp_path):
    bot = _run_invoice_flow(monkeypatch, tmp_path, username=None)

    caption = bot.photos[0]["caption"]
    assert f"👤 آیدی عددی: {CUSTOMER} — برای پنل {PANEL}" in caption


def test_the_last_known_username_is_used_when_the_live_one_is_gone(ledger, monkeypatch, tmp_path):
    bot_db.upsert_user(CUSTOMER, "matin_db", "Matin")

    bot = _run_invoice_flow(monkeypatch, tmp_path, username=None)

    caption = bot.photos[0]["caption"]
    assert f"👤 آیدی عددی: {CUSTOMER} (@matin_db) — برای پنل {PANEL}" in caption


def test_a_hand_raised_invoice_omits_the_panel(ledger, monkeypatch, tmp_path):
    invoice_id = bot_db.create_invoice(
        telegram_id=CUSTOMER,
        amount=AMOUNT,
        description="by hand",
        due_at=None,
        admin_username=None,
    )

    monkeypatch.setattr(
        wallet,
        "settings",
        SimpleNamespace(superadmin_id_list=[SUPERADMIN], media_dir=str(tmp_path / "media")),
    )
    monkeypatch.setattr(notify, "settings", SimpleNamespace(superadmin_id_list=[SUPERADMIN]))
    message = FakeMessage(CUSTOMER, "matin_test")
    bot = FakeBot()

    async def scenario():
        state = FSMContext(
            storage=MemoryStorage(),
            key=StorageKey(chat_id=1, user_id=1, bot_id=1),
        )
        await state.set_state(InvoicePayment.receipt)
        await state.update_data(invoice_id=invoice_id, invoice_amount=AMOUNT)
        await wallet.get_invoice_receipt(message, state, bot)

    asyncio.run(scenario())

    caption = bot.photos[0]["caption"]
    assert "برای پنل" not in caption
    assert f"👤 آیدی عددی: {CUSTOMER} (@matin_test)" in caption


def test_a_failed_lookup_still_delivers_the_plain_caption(ledger, monkeypatch, tmp_path):
    def broken(invoice_id):
        raise RuntimeError("sqlite busy")

    monkeypatch.setattr(bot_db, "get_invoice", broken)

    bot = _run_invoice_flow(monkeypatch, tmp_path)

    assert bot.photos, "the superadmin was never notified"
    caption = bot.photos[0]["caption"]
    assert "🧾 رسید فاکتور #" in caption
    assert f"👤 آیدی عددی: {CUSTOMER}" in caption
    assert f"💰 مبلغ: {AMOUNT:,} تومان" in caption
    assert "برای پنل" not in caption
