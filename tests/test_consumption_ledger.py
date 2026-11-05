from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import create_engine

from backend.bot import consumption_ledger as meter
from backend.db.engin import Base


GB = 1024**3
NOW = datetime(2026, 11, 6, 8, tzinfo=ZoneInfo("Asia/Tehran"))


@pytest.fixture
def billing_db(ledger):
    # Production uses one file for the panel balance and the bot invoice.
    engine = create_engine(f"sqlite:///{ledger.bot_config.sqlite_path}")
    Base.metadata.create_all(engine)
    with meter.transaction() as conn:
        conn.execute(
            """INSERT INTO admins
               (id, username, panel, hashed_password, traffic, initial_traffic, telegram_id)
               VALUES (1, 'reseller', 'marzban', 'test', 0, 0, 123)"""
        )
        meter.enroll(conn, 1, {})
        meter.grant(conn, 1, 1000 * GB)
    yield ledger
    engine.dispose()


def observe(name, limit, used=0, generation="first"):
    with meter.transaction() as conn:
        state = None if limit is None else meter.UserState(generation, limit * GB, used * GB)
        meter.observe(conn, 1, name, state)


def settle(week=0, price=100):
    now = NOW + timedelta(weeks=week)
    stamp = now.strftime("%G-%V")
    with meter.transaction() as conn:
        return meter.settle(conn, 1, stamp, now, price)


def test_bills_allocations_instead_of_grant_or_live_usage(billing_db):
    observe("user", 100, 50)
    result = settle()
    assert result.allocated == 100 * GB
    assert result.amount == 10_000
    assert billing_db.get_invoice(result.invoice_id).traffic_gb == 0
    assert settle() is None


def test_same_week_delete_preserves_only_used_quota(billing_db):
    observe("user", 100, 50)
    observe("user", None)
    assert settle().amount == 5_000
    with meter.transaction() as conn:
        assert meter.account(conn, 1)["available_bytes"] == 950 * GB


def test_discount_waits_for_payment_and_carries_across_weeks(billing_db):
    observe("original", 100, 50)
    original = settle()
    observe("original", None)
    observe("next", 20)
    assert settle(1).amount == 2_000

    assert billing_db.mark_invoice_paid(original.invoice_id)
    observe("small", 20)
    covered = settle(2)
    assert covered.discount == 20 * GB
    assert covered.invoice_id is None
    observe("new", 60)
    assert settle(3).amount == 3_000
    assert billing_db.get_invoice(original.invoice_id).amount == 10_000


def test_written_off_invoice_produces_no_discount(billing_db):
    observe("user", 100, 50)
    assert billing_db.cancel_invoice(settle().invoice_id)
    observe("user", None)
    observe("new", 100)
    assert settle(1).amount == 10_000


def test_mixed_quota_uses_paid_bytes_first_and_returns_weekly_bytes_first(billing_db):
    with meter.transaction() as conn:
        conn.execute("UPDATE admins SET traffic = traffic + ?", (100 * GB,))
    observe("mixed", 150, 110)
    observe("mixed", None)
    assert settle().amount == 1_000
    with meter.transaction() as conn:
        assert meter.account(conn, 1)["available_bytes"] == 990 * GB


def test_reduction_and_reset_account_for_both_reservations(billing_db):
    observe("user", 100, 50)
    observe("user", 60, 50)
    observe("user", 60, 0)
    observe("user", 60, 10)
    observe("user", None)
    assert settle().amount == 6_000


def test_reused_name_keeps_consumed_bytes_from_old_user(billing_db):
    observe("user", 100, 25)
    observe("user", 40, generation="replacement")
    assert settle().amount == 6_500


def test_failed_settlement_leaves_entries_intact(billing_db):
    observe("user", 100)
    with pytest.raises(meter.BillingDeferred):
        settle(price=0)
    assert settle().amount == 10_000


def test_rollback_reverts_invoice_and_allocation_state(billing_db):
    observe("user", 100)
    with pytest.raises(RuntimeError):
        with meter.transaction() as conn:
            meter.settle(conn, 1, NOW.strftime("%G-%V"), NOW, 100)
            raise RuntimeError("simulated interruption")
    assert billing_db.get_invoice(1) is None
    assert settle().amount == 10_000


class FakeMarzban:
    def __init__(self):
        self.users = {}
        self.listed = None
        self.reads = 0
        self.failure = None

    async def get_all_users_paginated(self, **kwargs):
        self.reads += 1
        if self.failure:
            raise self.failure
        return list(self.users.values()) if self.listed is None else self.listed

    async def get_billing_user(self, username):
        return self.users.get(username)


def upstream_user(name, limit, used=0, owner="reseller", generation="2026-11-01T00:00:00"):
    return {
        "username": name, "data_limit": limit * GB, "used_traffic": used * GB,
        "admin": {"username": owner}, "created_at": generation,
    }


@pytest.fixture
def upstream(billing_db, monkeypatch):
    from backend.bot import consumption
    with meter.transaction() as conn:
        conn.execute(
            """INSERT INTO panels (name, panel_type, url, username, password, is_active)
               VALUES ('marzban', 'marzban', 'https://marzban.test', 'sudo', 'test', 1)"""
        )
    billing_db.set_setting("price_per_gb", "100")
    api = FakeMarzban()
    monkeypatch.setattr(consumption, "APIService", lambda *args: api)
    return api


def cycle(now, stamp=None):
    import asyncio
    from unittest.mock import AsyncMock
    from backend.bot import consumption

    bot = AsyncMock()
    asyncio.run(consumption.run_cycle(bot, now, stamp, [999]))
    return bot


def test_hourly_direct_changes_and_confirmed_delete(upstream, billing_db):
    upstream.users["first"] = upstream_user("first", 100, 50)
    cycle(NOW - timedelta(hours=2))
    cycle(NOW - timedelta(hours=2, minutes=-15))
    assert upstream.reads == 1
    upstream.listed = []  # A listing omitted it, but the strict lookup finds it.
    cycle(NOW - timedelta(hours=1))
    with meter.transaction() as conn:
        assert meter.user_state(conn, 1, "first").used == 50 * GB
    upstream.users.clear()
    bot = cycle(NOW, NOW.strftime("%G-%V"))
    invoice = billing_db.list_pending_invoices()[0]
    assert invoice.amount == 5_000
    assert invoice.traffic_gb == 0
    assert any(call.args[0] == 123 for call in bot.send_message.await_args_list)
    assert any("آخرین مصرف ثبت‌شده" in call.args[1] for call in bot.send_message.await_args_list)


def test_friday_failure_retries_and_after_cutoff_allocations_wait(upstream, billing_db):
    from backend.services.marzban.api import MarzbanAPIError

    upstream.users["first"] = upstream_user("first", 100)
    upstream.failure = MarzbanAPIError("Incomplete panel read")
    stamp = NOW.strftime("%G-%V")
    cycle(NOW, stamp)
    assert not billing_db.list_pending_invoices()
    upstream.failure = None
    cycle(NOW + timedelta(minutes=10), stamp)
    assert billing_db.list_pending_invoices()[0].amount == 10_000
    upstream.users["second"] = upstream_user("second", 40)
    cycle(NOW + timedelta(hours=1), stamp)
    assert len(billing_db.list_pending_invoices()) == 1
    next_friday = NOW + timedelta(weeks=1)
    cycle(next_friday, next_friday.strftime("%G-%V"))
    assert sorted(i.amount for i in billing_db.list_pending_invoices()) == [4_000, 10_000]


def test_first_grant_preserves_ordinary_funding_and_disabling_keeps_settling(upstream, billing_db):
    import asyncio
    from backend.bot import consumption

    with meter.transaction() as conn:
        conn.execute(
            """INSERT INTO admins (id, username, panel, hashed_password, traffic, initial_traffic,
                                  telegram_id, is_active)
               VALUES (2, 'new', 'marzban', 'test', ?, ?, 456, 1)""",
            (100 * GB, 100 * GB),
        )
    upstream.users["old"] = upstream_user("old", 100, owner="new")
    billing_db.set_weekly_mode("new", "consumption")
    assert asyncio.run(consumption.grant(456, "new", 1_000)) == 1_100 * GB
    billing_db.set_weekly_enabled("new", False)
    with pytest.raises(meter.BillingDeferred):
        asyncio.run(consumption.grant(456, "new", 1_000))
    upstream.users["mixed"] = upstream_user("mixed", 200, owner="new")
    cycle(NOW, NOW.strftime("%G-%V"))
    invoice = billing_db.list_pending_invoices()[0]
    assert (invoice.telegram_id, invoice.amount) == (456, 10_000)


def test_recovery_after_a_timed_out_create_never_replays_upstream(upstream, billing_db, monkeypatch):
    import asyncio
    from requests import Timeout
    from backend.bot import consumption

    calls = []

    async def create(_):
        calls.append("create")
        upstream.users["user"] = upstream_user("user", 100)
        raise Timeout("the response was lost")

    with pytest.raises(Timeout):
        asyncio.run(consumption.mutate(1, "reseller", upstream, "user", "create", create, 100 * GB))
    with meter.transaction() as conn:
        assert consumption._pending(conn, 1) is not None
        assert meter.user_state(conn, 1, "user") is None

    monkeypatch.setattr(consumption, "INTENT_TIMEOUT", timedelta(0))
    code, _ = asyncio.run(consumption.mutate(1, "reseller", upstream, "user", "create", create, 100 * GB))
    assert code == 200
    assert calls == ["create"]
    assert settle().amount == 10_000


def test_observer_is_skipped_and_unmark_resumes_accounting(upstream, billing_db):
    upstream.users["user"] = upstream_user("user", 100)
    billing_db.mark_observer_admin("reseller", marked_by=1)
    cycle(NOW, NOW.strftime("%G-%V"))
    assert upstream.reads == 0
    assert not billing_db.list_pending_invoices()
    billing_db.unmark_observer_admin("reseller")
    cycle(NOW + timedelta(minutes=10), NOW.strftime("%G-%V"))
    assert billing_db.list_pending_invoices()[0].amount == 10_000


def test_dashboard_create_and_delete_use_journal_and_latest_usage(upstream, billing_db, monkeypatch):
    import asyncio
    from sqlalchemy.orm import Session
    from backend.schema._input import ClientInput
    from backend.services import task_handler
    from backend.services.marzban.api import APIService

    async def create(_self, payload):
        upstream.users[payload.email] = upstream_user(payload.email, 100)
        return 200

    async def delete(_self, username):
        upstream.users.pop(username)
        return 200

    async def get(_self, username):
        return await upstream.get_billing_user(username)

    monkeypatch.setattr(APIService, "create_user", create)
    monkeypatch.setattr(APIService, "delete_user", delete)
    monkeypatch.setattr(APIService, "get_billing_user", get)
    engine = create_engine(f"sqlite:///{billing_db.bot_config.sqlite_path}")
    with meter.transaction() as conn:
        conn.execute("UPDATE admins SET is_active = 1 WHERE id = 1")
    with Session(engine) as session:
        user_input = ClientInput(email="user", id="uuid", sub_id="sub", total=100 * GB, expiry_time=0)
        result = asyncio.run(task_handler.add_new_user("reseller", user_input, session))
        assert result.success
        upstream.users["user"]["used_traffic"] = 50 * GB
        result = asyncio.run(task_handler.delete_a_user("reseller", "user", session))
        assert result.success
    engine.dispose()
    assert settle().amount == 5_000


def test_reset_after_limit_dropped_below_usage_keeps_prior_consumption(billing_db):
    observe("user", 100, 50)
    observe("user", 20, 50)
    observe("user", 20, 0)
    assert settle().amount == 7_000


def test_direct_overdraft_keeps_its_own_ordinary_invoice(upstream, billing_db):
    upstream.users["over"] = upstream_user("over", 1_050)
    cycle(NOW - timedelta(hours=1))
    cycle(NOW, NOW.strftime("%G-%V"))
    invoices = billing_db.list_pending_invoices()
    assert sorted((i.amount, i.traffic_gb) for i in invoices) == [(5_000, 50), (100_000, 0)]


def test_concurrent_settlement_creates_one_invoice(billing_db):
    from concurrent.futures import ThreadPoolExecutor

    observe("user", 100)
    with ThreadPoolExecutor(max_workers=2) as workers:
        results = list(workers.map(lambda _: settle(), range(2)))
    assert sum(result is not None for result in results) == 1
    assert len(billing_db.list_pending_invoices()) == 1


def test_admin_deletion_cannot_discard_live_consumption_quota(billing_db):
    from sqlalchemy.orm import Session
    from backend.db import crud

    engine = create_engine(f"sqlite:///{billing_db.bot_config.sqlite_path}")
    with Session(engine) as session:
        with pytest.raises(meter.BillingDeferred):
            crud.remove_admin(session, 1)
    engine.dispose()
    with meter.transaction() as conn:
        assert meter.account(conn, 1)["available_bytes"] == 1_000 * GB
