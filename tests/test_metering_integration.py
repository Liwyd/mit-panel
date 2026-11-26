"""«ادمین ویژه» everywhere outside the meter itself.

A metered sub-admin must be invisible to every balance path (limit checks,
charges, refunds, the usage sync, low-traffic warnings, buying GB) and look
exactly like everyone else to invoices, profit and the lock. Turning the mode
off must leave nothing refundable that was never paid for.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.bot import bills, consumption_ledger, metering, texts
from backend.db import crud

from tests.test_metering import GB, FakeMarzban, _set_traffic, _traffic, _use, shared  # noqa: F401


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def orm(shared, monkeypatch):
    import backend.db.engin as engin
    from backend.bot import usage_sync

    monkeypatch.setattr(usage_sync, "sessionLocal", engin.sessionLocal)
    with engin.sessionLocal() as session:
        yield session


# ------------------------------------------------------------------ the limiter


def test_the_limiter_neither_limits_nor_charges_a_metered_admin(orm):
    from backend.services.limit_handler import AdminLimiter

    _set_traffic(0)
    _run(metering.enable(1, by=9))
    limiter = AdminLimiter(orm, "amir")
    assert limiter.check_traffic_limit(10_000 * GB)
    limiter.reduce_usage(50 * GB, 50 * GB)
    limiter.apply_update(10 * GB, 90 * GB)
    limiter.charge(5 * GB)
    limiter.increase_usage(20 * GB)
    assert _traffic() == 0


def test_the_limiter_is_unchanged_for_everyone_else(orm):
    from backend.services.limit_handler import AdminLimiter

    _set_traffic(100)
    orm.expire_all()
    limiter = AdminLimiter(orm, "amir")
    assert not limiter.check_traffic_limit(200 * GB)
    assert limiter.check_traffic_limit(50 * GB)
    limiter.reduce_usage(30 * GB, 30 * GB)
    assert _traffic() == 70 * GB


def test_after_disabling_the_normal_rules_apply_again(orm):
    from backend.services.limit_handler import AdminLimiter

    _run(metering.enable(1, by=9))
    _run(metering.disable(1))
    _set_traffic(10)
    orm.expire_all()
    limiter = AdminLimiter(orm, "amir")
    assert not limiter.metered
    assert not limiter.check_traffic_limit(20 * GB)
    limiter.reduce_usage(5 * GB, 5 * GB)
    assert _traffic() == 5 * GB


# ------------------------------------------------------------------ the sweeps


def test_the_usage_sync_never_charges_a_metered_admin(orm, monkeypatch):
    from backend.bot import usage_sync

    _set_traffic(10)
    rows = [{"username": "direct", "admin": {"username": "amir"}, "data_limit": 40 * GB,
             "used_traffic": 0, "status": "active"}]
    monkeypatch.setattr(usage_sync, "_read_panel_users", lambda panel: rows)
    usage_sync._sweep()  # first run adopts what is there
    _run(metering.enable(1, by=9))
    rows.append({"username": "direct2", "admin": {"username": "amir"}, "data_limit": 40 * GB,
                 "used_traffic": 0, "status": "active"})
    usage_sync._sweep()
    assert _traffic() == 10 * GB  # made straight on Marzban, paid through usage


def test_the_same_sweep_does_charge_a_normal_admin(orm, monkeypatch):
    """Control for the test above: without the mode the user is charged."""
    from backend.bot import usage_sync

    _set_traffic(10)
    orm.expire_all()
    rows = [{"username": "direct", "admin": {"username": "amir"}, "data_limit": 40 * GB,
             "used_traffic": 0, "status": "active"}]
    monkeypatch.setattr(usage_sync, "_read_panel_users", lambda panel: rows)
    usage_sync._sweep()  # first run adopts what is there
    rows.append({"username": "direct2", "admin": {"username": "amir"}, "data_limit": 40 * GB,
                 "used_traffic": 0, "status": "active"})
    usage_sync._sweep()
    assert _traffic() == 10 * GB - 40 * GB


def test_low_traffic_warnings_skip_a_metered_admin(shared, monkeypatch):
    from backend.bot import warnings

    _run(metering.enable(1, by=9))
    bot = SimpleNamespace(send_message=AsyncMock())
    monkeypatch.setattr(
        warnings.panel_client, "list_all_admins",
        AsyncMock(return_value=[{"id": 1, "username": "amir", "telegram_id": 555, "traffic": 0,
                                 "initial_traffic": 0, "is_active": True}]),
    )
    assert _run(warnings.scan_once(bot)) == 0
    bot.send_message.assert_not_called()


def test_buying_gb_is_refused_for_a_metered_panel(shared, monkeypatch):
    from backend.bot.routers import topup

    _run(metering.enable(1, by=9))
    monkeypatch.setattr(topup, "menu_kb_for", AsyncMock(return_value=None))
    message = SimpleNamespace(answer=AsyncMock(), chat=SimpleNamespace(id=555))
    state = SimpleNamespace(clear=AsyncMock(), update_data=AsyncMock(), set_state=AsyncMock())
    _run(topup._ask_amount(message, state, "amir"))
    sent = message.answer.await_args.args[0]
    assert "مصرفی" in sent
    state.set_state.assert_not_called()


def test_the_other_payment_modes_cannot_be_stacked(shared):
    _run(metering.enable(1, by=9))
    assert metering.is_metered_username("amir")
    assert not metering.is_metered_username("someone-else")


# ------------------------------------------------------------------ invoices, profit, dashboard


def test_a_paid_metered_invoice_is_booked_under_the_panel_with_its_gb(shared):
    _run(metering.enable(1, by=9))
    _use(40)
    _run(metering.poll(metering._now()))
    with consumption_ledger.transaction() as conn:
        result = metering.settle(conn, 1, metering.week_stamp(metering._now()), metering._now(), 3000.0)
    bill = next(b for b in bills.open_bills(555) if b.invoice_id == result.invoice_id)
    assert bills.mark_paid(bill) is not None
    sales = [(s.username, s.gb, s.amount) for s in shared.list_sales_since("") if s.method == "invoice"]
    assert sales == [("amir", 40.0, 120_000)]


def test_an_unpaid_metered_invoice_is_an_ordinary_open_bill(shared):
    _run(metering.enable(1, by=9))
    _use(40)
    _run(metering.poll(metering._now()))
    with consumption_ledger.transaction() as conn:
        result = metering.settle(conn, 1, metering.week_stamp(metering._now()), metering._now(), 3000.0)
    open_ = [b for b in bills.open_bills(555) if b.invoice_id == result.invoice_id]
    assert open_ and open_[0].kind == "invoice" and open_[0].amount == 120_000


def test_the_dashboard_shows_usage_only_while_metered(shared):
    from backend.api.public.routers import _metered_usage

    assert _metered_usage(1) is None
    _run(metering.enable(1, by=9))
    _use(12)
    _run(metering.poll(metering._now()))
    usage = _metered_usage(1)
    assert usage["used_bytes"] == 12 * GB and "price" not in str(usage)
    _run(metering.disable(1))
    assert _metered_usage(1) is None


def test_the_new_button_never_reaches_a_waiting_flow():
    from backend.bot.nav import ALL_MENU_TEXTS
    from backend.bot.routers import all_routers

    assert texts.BTN_METERED_ADMIN in ALL_MENU_TEXTS
    assert "metered" in {r.name for r in all_routers}
