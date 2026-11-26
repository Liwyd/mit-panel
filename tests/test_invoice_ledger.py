"""A paid invoice goes into the sales ledger under its panel.

An invoice used to be booked with no panel and 0 GB unless paying it granted
traffic, so the profit report showed its money as «بدون پنل» with no cost —
100% profit — while the panel it was for looked like a loss. Every payment
path (card receipt, «پرداخت شد», Black Friday wallet) now books the panel and
the GB the invoice sold through `db.invoice_ledger_fields`.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock

from backend.bot import approvals, bills


class FakeBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, **kwargs):
        self.sent.append((chat_id, text))


def _invoice_sales(ledger):
    return [
        (s.username, s.gb, s.amount)
        for s in ledger.list_sales_since("")
        if s.method == "invoice"
    ]


def _pay_by_receipt(ledger, invoice_id, monkeypatch):
    topup = AsyncMock()
    monkeypatch.setattr(approvals.panel_client, "topup", topup)
    request = ledger.create_request(
        admin_telegram_id=111,
        admin_username=None,
        requested_gb=0,
        toman_amount=ledger.get_invoice(invoice_id).amount,
        receipt_path="",
        kind="invoice",
        invoice_id=invoice_id,
    )
    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    return topup


def test_ledger_fields_for_every_kind_of_invoice(ledger):
    hand = ledger.get_invoice(ledger.create_invoice(
        telegram_id=1, amount=10, description="x", due_at=None, admin_username="kara"))
    usage = ledger.get_invoice(ledger.create_invoice(
        telegram_id=1, amount=10, description="x", due_at=None, admin_username="hkab",
        usage_gb=86.4))
    grant = ledger.get_invoice(ledger.create_invoice(
        telegram_id=1, amount=10, description="x", due_at=None, admin_username="fuad",
        traffic_gb=50))
    loose = ledger.get_invoice(ledger.create_invoice(
        telegram_id=1, amount=10, description="x", due_at=None))

    assert ledger.invoice_ledger_fields(hand, grants_gb=False) == ("kara", 0.0)
    assert ledger.invoice_ledger_fields(usage, grants_gb=False) == ("hkab", 86.4)
    assert ledger.invoice_ledger_fields(grant, grants_gb=True) == ("fuad", 50.0)
    assert ledger.invoice_ledger_fields(loose, grants_gb=False) == (None, 0.0)
    assert ledger.invoice_ledger_fields(None, grants_gb=False) == (None, 0.0)


def test_a_hand_raised_invoice_is_booked_under_its_panel(ledger, monkeypatch):
    invoice = ledger.create_invoice(
        telegram_id=111, amount=1_300_000, description="شارژ پنل ۵۰۰ گیگ",
        due_at=None, admin_username="mehranz",
    )
    topup = _pay_by_receipt(ledger, invoice, monkeypatch)
    assert topup.await_count == 0  # it grants nothing
    assert _invoice_sales(ledger) == [("mehranz", 0.0, 1_300_000)]


def test_a_usage_invoice_is_costed_with_the_gb_it_bills(ledger, monkeypatch):
    invoice = ledger.create_invoice(
        telegram_id=111, amount=250_545, description="مصرف هفتگی پنل Hkab",
        due_at=None, admin_username="Hkab", usage_gb=86.4,
    )
    topup = _pay_by_receipt(ledger, invoice, monkeypatch)
    assert topup.await_count == 0  # the traffic was used already
    assert _invoice_sales(ledger) == [("Hkab", 86.4, 250_545)]


def test_an_invoice_that_grants_traffic_keeps_its_gb(ledger, monkeypatch):
    invoice = ledger.create_invoice(
        telegram_id=111, amount=100_000, description="x", due_at=None,
        admin_username="fuad", traffic_gb=40,
    )
    topup = _pay_by_receipt(ledger, invoice, monkeypatch)
    assert topup.await_count == 1
    assert _invoice_sales(ledger) == [("fuad", 40.0, 100_000)]


def test_marking_an_invoice_paid_books_it_under_its_panel(ledger):
    invoice = ledger.create_invoice(
        telegram_id=111, amount=500_000, description="بدهی پنل ۲۰۰ گیگ",
        due_at=None, admin_username="saedport", usage_gb=0,
    )
    bill = next(b for b in bills.open_bills(111) if b.invoice_id == invoice)
    assert bills.mark_paid(bill) is not None
    assert _invoice_sales(ledger) == [("saedport", 0.0, 500_000)]


def test_only_an_invoice_with_no_panel_stays_panel_less(ledger):
    invoice = ledger.create_invoice(
        telegram_id=111, amount=292_350, description="نگهداری ربات", due_at=None,
    )
    bill = next(b for b in bills.open_bills(111) if b.invoice_id == invoice)
    bills.mark_paid(bill)
    assert _invoice_sales(ledger) == [(None, 0.0, 292_350)]


def test_the_correction_script_attributes_only_sure_matches(ledger):
    import importlib.util
    import sqlite3
    from pathlib import Path

    spec = importlib.util.spec_from_file_location(
        "attribute_invoice_sales", Path(__file__).parent.parent / "scripts" / "attribute_invoice_sales.py"
    )
    script = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(script)

    panel_inv = ledger.create_invoice(
        telegram_id=111, amount=1_300_000, description="x", due_at=None, admin_username="mehranz")
    loose_inv = ledger.create_invoice(telegram_id=222, amount=292_350, description="x", due_at=None)
    for inv in (panel_inv, loose_inv):
        ledger.mark_invoice_paid(inv)
    # The rows the old code wrote: no panel, 0 GB.
    ledger.record_sale(telegram_id=111, username=None, gb=0, amount=1_300_000, method="invoice")
    ledger.record_sale(telegram_id=222, username=None, gb=0, amount=292_350, method="invoice")

    conn = sqlite3.connect(ledger.bot_config.sqlite_path)
    changes = script.plan(conn, "1970-01-01T00:00:00+00:00")
    assert [(panel, gb) for _, panel, gb in changes] == [("mehranz", 0.0)]
    assert script.plan(conn, "2999-01-01T00:00:00+00:00") == []
