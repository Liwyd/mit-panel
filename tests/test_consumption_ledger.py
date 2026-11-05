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
