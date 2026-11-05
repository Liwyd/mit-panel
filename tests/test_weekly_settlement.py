"""Compatibility checks for invoices and delayed settlement."""

import asyncio
import sqlite3
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot import db, weekly
from backend.bot.routers import topup

STAMP = "2026-42"


def test_consumption_invoice_uniqueness_is_enforced(ledger):
    db.create_invoice(
        telegram_id=1, amount=100, description="x", due_at=None,
        admin_username="fuad", week_stamp=STAMP,
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.create_invoice(
            telegram_id=1, amount=100, description="y", due_at=None,
            admin_username="fuad", week_stamp=STAMP,
        )
    # A different week, or a panel-less invoice, is unaffected.
    db.create_invoice(
        telegram_id=1, amount=100, description="x", due_at=None,
        admin_username="fuad", week_stamp="2026-43",
    )
    db.create_invoice(telegram_id=1, amount=100, description="hand", due_at=None)


def test_idempotency_match_is_exact_not_a_substring(ledger):
    db.create_invoice(
        telegram_id=1, amount=100, description="x", due_at=None,
        admin_username="fuad", week_stamp="2026-41",
    )
    assert db.consumption_invoice_exists("fuad", "2026-41")
    assert not db.consumption_invoice_exists("fuadx", "2026-41")
    assert not db.consumption_invoice_exists("fuad", "2026-42")


def test_delayed_topup_bills_full_price_and_friday_settles_existing_debt(ledger, monkeypatch):
    ledger.set_weekly_mode("reseller", "delayed")
    grant = AsyncMock(return_value={"new_traffic_bytes": 1024**4})
    monkeypatch.setattr(topup.panel_client, "topup", grant)
    monkeypatch.setattr(topup.consumption, "grant", AsyncMock(side_effect=AssertionError("wrong mode")))
    call = SimpleNamespace(
        from_user=SimpleNamespace(id=123), answer=AsyncMock(),
        message=SimpleNamespace(answer=AsyncMock()),
    )
    state = SimpleNamespace(get_data=AsyncMock(return_value={
        "panel_username": "reseller", "total_price": 123_000, "amount_gb": 1024,
    }), clear=AsyncMock())
    bot = SimpleNamespace(send_message=AsyncMock())

    asyncio.run(topup.pay_weekly_credit(call, state, bot))
    grant.assert_awaited_once_with(123, 1024, username="reseller")
    assert ledger.get_debt("reseller") == 123_000
    assert ledger.list_pending_invoices() == []

    ledger.add_wallet_balance(123, 123_000)
    asyncio.run(weekly.run_settlement(bot))
    assert ledger.get_debt("reseller") == 0
    assert ledger.get_wallet_balance(123) == 0
    assert ledger.list_pending_invoices() == []


def test_supervised_restarts_a_crashed_runner(monkeypatch):
    from backend.bot import service

    monkeypatch.setattr(service, "SUPERVISOR_RESTART_DELAY", 0.001)
    calls = []

    async def crashy():
        calls.append(1)
        if len(calls) >= 2:
            raise asyncio.CancelledError
        raise RuntimeError("boom")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service._supervised("crashy", crashy))
    assert len(calls) == 2


def test_supervised_restarts_a_normally_returning_runner(monkeypatch):
    from backend.bot import service

    monkeypatch.setattr(service, "SUPERVISOR_RESTART_DELAY", 0.001)
    calls = []

    async def returns():
        calls.append(1)
        if len(calls) >= 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service._supervised("returns", returns))
    assert len(calls) == 2
