"""Safety checks for dashboard-managed top-up bot copy and receipt review."""

import asyncio

from backend.bot import content, texts
from backend.bot.approvals import reject_request


def test_text_override_requires_the_same_placeholders(monkeypatch):
    monkeypatch.setattr(
        content,
        "get_settings",
        lambda: {
            content.TEXT_OVERRIDES_KEY: {
                "BALANCE_TEXT": "مانده: {remaining_gb:.2f} از {initial_gb:.2f}",
                "INVOICE_TEXT": "متغیرهای اشتباه {not_a_real_field}",
            }
        },
    )

    assert content.configured_overrides() == {
        "BALANCE_TEXT": "مانده: {remaining_gb:.2f} از {initial_gb:.2f}"
    }
    assert content.fields(texts.BALANCE_TEXT) == ["remaining_gb", "initial_gb"]


def test_dashboard_rejection_uses_the_atomic_review_path(ledger, tmp_path):
    receipt = tmp_path / "receipt.jpg"
    receipt.write_bytes(b"receipt")
    request_id = ledger.create_request(
        admin_telegram_id=123,
        admin_username="alice",
        requested_gb=10,
        toman_amount=100_000,
        receipt_path=str(receipt),
    )

    class FakeBot:
        def __init__(self):
            self.messages = []

        async def send_message(self, chat_id, text):
            self.messages.append((chat_id, text))

    bot = FakeBot()
    outcome = asyncio.run(reject_request(bot, request_id, -1, "خوانا نیست"))

    assert outcome.ok
    assert ledger.get_request(request_id).status == "rejected"
    assert ledger.get_request(request_id).reject_reason == "خوانا نیست"
    assert not receipt.exists()
    assert bot.messages[0][0] == 123
