"""A shop panel request must reach the superadmins, whatever else fails.

The notification once never fired at all: the handler read `current_admins`,
a name that only exists in a different function, so every request crashed
after the customer had been told their request was submitted (production,
2026-11-03..2026-11-11). These tests pin the whole receipt path: the request
is stored, the customer is answered, and the superadmin gets the photo even
when the panel API is down at that exact moment.
"""

import asyncio
from types import SimpleNamespace

from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.base import StorageKey
from aiogram.fsm.storage.memory import MemoryStorage

from backend.bot import db as bot_db
from backend.bot import notify
from backend.bot import texts
from backend.bot.routers import shop
from backend.bot.states import ShopBuy

CUSTOMER = 1131519306
SUPERADMIN = 1451599691
PANEL = "touch"


class FakePhoto:
    file_id = "photo-file-id"


class FakeMessage:
    def __init__(self, user_id: int, username: str):
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


def _run_receipt_flow(ledger, monkeypatch, tmp_path, get_admins) -> tuple[FakeMessage, FakeBot]:
    monkeypatch.setattr(
        shop,
        "settings",
        SimpleNamespace(superadmin_id_list=[SUPERADMIN], media_dir=str(tmp_path / "media")),
    )
    monkeypatch.setattr(notify, "settings", SimpleNamespace(superadmin_id_list=[SUPERADMIN]))
    monkeypatch.setattr(shop.panel_client, "get_admins", get_admins)
    message = FakeMessage(CUSTOMER, "matin_test")
    bot = FakeBot()

    async def scenario() -> tuple[FakeMessage, FakeBot]:
        state = FSMContext(
            storage=MemoryStorage(),
            key=StorageKey(chat_id=1, user_id=1, bot_id=1),
        )
        await state.set_state(ShopBuy.receipt)
        await state.update_data(
            shop_panel=PANEL,
            shop_gb=200.0,
            shop_referral_code_id=None,
            shop_username="matinsh_new",
            shop_password="pass1234",
        )
        await shop.shop_get_receipt(message, state, bot)
        return message, bot

    message, bot = asyncio.run(scenario())
    return message, bot


def test_the_superadmin_gets_the_request_while_the_panel_api_is_down(ledger, monkeypatch, tmp_path):
    async def broken(*args, **kwargs):
        raise RuntimeError("panel unreachable")

    message, bot = _run_receipt_flow(ledger, monkeypatch, tmp_path, broken)

    assert bot.photos, "the superadmin was never notified"
    assert bot.photos[0]["chat_id"] == SUPERADMIN
    assert texts.PANEL_REQUEST_HEADER.format(username="matin_test", telegram_id=CUSTOMER) in bot.photos[0]["caption"]
    assert ledger.get_pending_panel_request(CUSTOMER) is not None
    assert texts.SHOP_REQUEST_SUBMITTED in message.answers[0]


def test_an_existing_owner_gets_their_next_panel_number(ledger, monkeypatch, tmp_path):
    bot_db.ensure_panel_metadata(CUSTOMER, ["matinsh"])

    async def down(*args, **kwargs):
        raise RuntimeError("panel unreachable")

    _, bot = _run_receipt_flow(ledger, monkeypatch, tmp_path, down)

    # Degraded path: the number falls back to the owner's last known panel.
    assert "شماره پنل: 2" in bot.photos[0]["caption"]


def test_a_healthy_panel_api_feeds_the_number_allocation(ledger, monkeypatch, tmp_path):
    async def healthy(user_id):
        return [{"username": "matinsh"}]

    _, bot = _run_receipt_flow(ledger, monkeypatch, tmp_path, healthy)

    assert bot_db.get_panel_metadata("matinsh")["panel_number"] == 1
    assert bot.photos[0]["chat_id"] == SUPERADMIN
