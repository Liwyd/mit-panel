"""«ادمین ویژه»: billing a sub-admin for the traffic their users really use.

Production keeps the bot tables and `admins` in one SQLite file, and the
settlement relies on that (prepaid draw + invoice + mark in one transaction),
so these tests do too. Marzban is a fake exposing the two calls the module
makes: every admin's `users_usage`, and the admin's users on disable.
"""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.bot import metering
from backend.bot import consumption_ledger
from backend.db.engin import Base

GB = 1024**3
FRIDAY = datetime(2026, 11, 27, 6, 0, tzinfo=timezone.utc)  # 09:30 Tehran, Friday


def _run(coro):
    return asyncio.run(coro)


class FakeMarzban:
    counters: dict[str, int] = {}
    users: list[dict] = []
    fail = False
    fail_users = False

    def __init__(self, url, username, password, inbounds=None):
        pass

    async def get_admin_usages(self):
        if FakeMarzban.fail:
            raise RuntimeError("panel down")
        return dict(FakeMarzban.counters)

    async def get_all_users_paginated(self, page_size=500, page_delay=0.0, *, owners=None):
        if FakeMarzban.fail_users:
            raise RuntimeError("Incomplete user read")
        return [dict(u) for u in FakeMarzban.users]


@pytest.fixture()
def shared(ledger, monkeypatch):
    engine = create_engine(f"sqlite:///{ledger.bot_config.sqlite_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    import backend.db.engin as engin

    monkeypatch.setattr(engin, "sessionLocal", factory)
    with consumption_ledger.transaction() as conn:
        conn.execute(
            "INSERT INTO panels (id, panel_type, name, url, username, password, is_active) "
            "VALUES (1, 'marzban', 'touch', 'http://m', 'sudo', 'pw', 1)"
        )
        conn.execute(
            "INSERT INTO panels (id, panel_type, name, url, username, password, is_active) "
            "VALUES (2, 'guard', 'g', 'http://g', 'a', 'b', 1)"
        )
        conn.execute(
            "INSERT INTO admins (id, username, panel, hashed_password, traffic, initial_traffic, telegram_id, is_active) "
            "VALUES (1, 'amir', 'touch', 'h', 0, 0, 555, 1)"
        )
    monkeypatch.setattr(metering.db, "get_effective_price", lambda _u: 3000.0)
    FakeMarzban.counters = {"Amir": 500 * GB}
    FakeMarzban.users = []
    FakeMarzban.fail = FakeMarzban.fail_users = False
    monkeypatch.setattr(metering, "MarzbanAPI", FakeMarzban)
    yield ledger
    engine.dispose()


def _set_traffic(gb: float) -> None:
    with consumption_ledger.transaction() as conn:
        conn.execute("UPDATE admins SET traffic = ? WHERE id = 1", (int(gb * GB),))


def _traffic() -> int:
    with metering.db._connect() as conn:
        return conn.execute("SELECT traffic FROM admins WHERE id = 1").fetchone()["traffic"]


def _use(gb: float) -> None:
    FakeMarzban.counters["Amir"] += int(gb * GB)


def _settle(now=FRIDAY, *, final=False, stamp=None):
    _run(metering.poll(now))
    with consumption_ledger.transaction() as conn:
        return metering.settle(conn, 1, stamp or metering.week_stamp(now), now, 3000.0, final=final)


# ------------------------------------------------------------------ enabling


def test_enabling_takes_the_live_counter_as_baseline(shared):
    info = _run(metering.enable(1, by=9, now=FRIDAY))
    assert info["counter_bytes"] == 500 * GB
    assert metering.is_metered(1)
    assert metering.usage(1)["used_bytes"] == 0
    _use(40)
    _run(metering.poll(FRIDAY))
    u = metering.usage(1)
    assert (u["used_bytes"], u["unsettled_bytes"]) == (40 * GB, 40 * GB)


@pytest.mark.parametrize("setup,match", [
    ("guard", "مرزبان"),
    ("inactive", "غیرفعال"),
    ("delayed", "تأخیر"),
    ("unreadable", "مرزبان"),
    ("missing", "پیدا نشد"),
])
def test_enabling_is_refused_without_changing_anything(shared, setup, match):
    with consumption_ledger.transaction() as conn:
        if setup == "guard":
            conn.execute("UPDATE admins SET panel = 'g' WHERE id = 1")
        if setup == "inactive":
            conn.execute("UPDATE admins SET is_active = 0 WHERE id = 1")
    if setup == "delayed":
        shared.set_weekly_mode("amir", "delayed")
    if setup == "unreadable":
        FakeMarzban.fail = True
    if setup == "missing":
        FakeMarzban.counters = {"someone": 1}
    with pytest.raises(metering.MeteringError, match=match):
        _run(metering.enable(1, by=9))
    assert not metering.is_metered(1)


def test_enabling_twice_is_refused(shared):
    _run(metering.enable(1, by=9))
    with pytest.raises(metering.MeteringError):
        _run(metering.enable(1, by=9))


# ------------------------------------------------------------------ settling


def test_a_week_of_usage_is_invoiced_at_the_panel_price(shared):
    _run(metering.enable(1, by=9, now=FRIDAY - timedelta(days=7)))
    _use(100)
    result = _settle()
    assert (result.delta, result.covered, result.billable) == (100 * GB, 0, 100 * GB)
    assert result.amount == 300_000
    invoice = shared.get_invoice(result.invoice_id)
    assert (invoice.admin_username, invoice.usage_gb, invoice.traffic_gb) == ("amir", 100.0, 0.0)
    assert invoice.telegram_id == 555 and invoice.due_at is not None
    assert metering.usage(1)["unsettled_bytes"] == 0


def test_prepaid_gb_is_used_before_anything_is_invoiced(shared):
    _set_traffic(120)
    _run(metering.enable(1, by=9))
    _use(80)
    first = _settle()
    assert (first.covered, first.billable, first.invoice_id) == (80 * GB, 0, None)
    assert _traffic() == 40 * GB
    _use(100)
    second = _settle(FRIDAY + timedelta(days=7))
    assert (second.covered, second.billable) == (40 * GB, 60 * GB)
    assert _traffic() == 0
    assert shared.get_invoice(second.invoice_id).usage_gb == 60.0


def test_a_grant_during_the_mode_adds_to_prepaid(shared):
    _run(metering.enable(1, by=9))
    _set_traffic(30)  # superadmin grant
    _use(50)
    result = _settle()
    assert (result.covered, result.billable) == (30 * GB, 20 * GB)


def test_a_negative_balance_is_left_alone(shared):
    _set_traffic(-10)
    _run(metering.enable(1, by=9))
    _use(10)
    result = _settle()
    assert (result.covered, result.billable) == (0, 10 * GB)
    assert _traffic() == -10 * GB


def test_the_same_week_is_never_billed_twice(shared):
    _run(metering.enable(1, by=9))
    _use(10)
    first = _settle()
    _use(5)
    again = _settle()
    assert first.invoice_id and again.skipped
    # the 5 GB used after the bill waits for next week
    assert metering.usage(1)["unsettled_bytes"] == 5 * GB


def test_a_tiny_week_is_carried_not_invoiced(shared):
    _run(metering.enable(1, by=9))
    _use(0.1)  # 300 toman
    result = _settle()
    assert result.invoice_id is None and result.carried == int(0.1 * GB)
    assert metering.usage(1)["unsettled_bytes"] == int(0.1 * GB)


def test_a_counter_reset_never_bills_twice_or_negative(shared):
    _run(metering.enable(1, by=9))
    _use(30)
    _run(metering.poll(FRIDAY))
    FakeMarzban.counters["Amir"] = 0  # sudo reset admin usage
    notes = _run(metering.poll(FRIDAY))
    assert notes and "amir" in notes[0]
    _use(20)
    result = _settle()
    assert result.delta == 50 * GB  # 30 before the reset + 20 after


def test_an_unreadable_panel_changes_nothing(shared):
    _run(metering.enable(1, by=9))
    FakeMarzban.fail = True
    assert _run(metering.poll(FRIDAY)) == []
    assert metering.usage(1)["unsettled_bytes"] == 0


def test_missing_telegram_id_defers_the_whole_settlement(shared):
    _set_traffic(10)
    _run(metering.enable(1, by=9))
    with consumption_ledger.transaction() as conn:
        conn.execute("UPDATE admins SET telegram_id = NULL WHERE id = 1")
    _use(50)
    with pytest.raises(metering.MeteringError):
        _settle()
    # rolled back: prepaid untouched, usage still unsettled
    assert _traffic() == 10 * GB
    assert metering.usage(1)["unsettled_bytes"] == 50 * GB


def test_friday_settles_once_and_reports_deferrals_once(shared, monkeypatch):
    _run(metering.enable(1, by=9))
    _use(10)
    with consumption_ledger.transaction() as conn:
        conn.execute("UPDATE admins SET telegram_id = NULL WHERE id = 1")
    first = _run(metering.settle_week(FRIDAY))
    second = _run(metering.settle_week(FRIDAY + timedelta(minutes=5)))
    assert isinstance(first[0][1], metering.MeteringError)
    assert second[0][1] is None
    with consumption_ledger.transaction() as conn:
        conn.execute("UPDATE admins SET telegram_id = 555 WHERE id = 1")
    third = _run(metering.settle_week(FRIDAY + timedelta(minutes=10)))
    assert third[0][1].invoice_id
    assert _run(metering.settle_week(FRIDAY + timedelta(minutes=15))) == []


def test_observers_are_not_billed(shared, monkeypatch):
    _run(metering.enable(1, by=9))
    _use(10)
    monkeypatch.setattr(metering.db, "list_observer_admins", lambda: ["amir"])
    assert _run(metering.settle_week(FRIDAY)) == []


# ------------------------------------------------------------------ disabling


def _user(name, limit_gb, used_gb=0, owner="amir"):
    return {"username": name, "admin": {"username": owner},
            "data_limit": int(limit_gb * GB), "used_traffic": int(used_gb * GB)}


def test_quota_sold_before_the_mode_is_never_billed_again(shared):
    # 100 GB config already paid for, 20 used: 80 GB of it is still prepaid.
    FakeMarzban.users = [_user("old", 100, 20)]
    info = _run(metering.enable(1, by=9))
    assert info["credit_bytes"] == 80 * GB
    _use(80)  # the old user uses what was paid for
    first = _settle()
    assert (first.covered, first.billable, first.invoice_id) == (80 * GB, 0, None)
    _use(30)  # anything beyond it is billed
    second = _settle(FRIDAY + timedelta(days=7))
    assert second.billable == 30 * GB


def test_credit_is_used_before_the_balance(shared):
    _set_traffic(50)
    FakeMarzban.users = [_user("old", 40)]
    _run(metering.enable(1, by=9))
    _use(60)
    result = _settle()
    assert (result.covered, result.billable) == (60 * GB, 0)
    assert _traffic() == 30 * GB  # 40 from credit, 20 from the balance
    assert metering.usage(1)["prepaid_bytes"] == 30 * GB


def test_disabling_buys_back_quota_live_users_keep(shared):
    _run(metering.enable(1, by=9))
    _use(5)
    # made during the mode, nothing paid: 50 GB limit, 5 used -> 45 still usable
    FakeMarzban.users = [_user("new", 50, 5), _user("foreign", 9, owner="x")]
    preview = _run(metering.preview_disable(1))
    assert (preview["billable"], preview["shortfall"]) == (50 * GB, 45 * GB)
    assert preview["amount"] == 150_000
    result = _run(metering.disable(1))
    assert (result.billable, result.shortfall) == (50 * GB, 45 * GB)
    invoice = shared.get_invoice(result.invoice_id)
    assert invoice.usage_gb == 50.0 and invoice.amount == 150_000
    assert not metering.is_metered(1)
    assert metering.usage(1) is None
    with metering.db._connect() as conn:
        rows = {r["username"]: (r["source"], r["data_limit"]) for r in conn.execute("SELECT * FROM marzban_users")}
    assert rows == {"new": ("bot", 50 * GB)}


def test_disabling_returns_unused_credit_to_the_balance(shared):
    FakeMarzban.users = [_user("old", 100, 0)]
    _run(metering.enable(1, by=9))  # credit 100
    _use(30)  # the old user used 30 of it
    FakeMarzban.users = []  # ...then was deleted: 70 GB paid and never used
    preview = _run(metering.preview_disable(1))
    assert preview["billable"] == 0 and preview["balance_after"] == 70 * GB
    result = _run(metering.disable(1))
    assert result.invoice_id is None
    assert _traffic() == 70 * GB


def test_disabling_keeps_an_existing_debt(shared):
    _set_traffic(-10)
    _run(metering.enable(1, by=9))
    FakeMarzban.users = [_user("u", 20, 0)]
    result = _run(metering.disable(1))
    assert result.shortfall == 20 * GB
    assert _traffic() == -10 * GB  # the old debt is untouched, still invoiced elsewhere


def test_the_ledger_is_brought_in_line_on_disable(shared):
    with consumption_ledger.transaction() as conn:
        conn.execute(
            "INSERT INTO marzban_users (username, owner, data_limit, source) VALUES ('old', 'amir', 10, 'bot')"
        )
    FakeMarzban.users = [_user("old", 10)]
    _run(metering.enable(1, by=9))
    FakeMarzban.users = [_user("old", 60)]  # raised straight on Marzban during the mode
    _run(metering.disable(1))
    with metering.db._connect() as conn:
        row = conn.execute("SELECT * FROM marzban_users WHERE username = 'old'").fetchone()
    # bought back at 60, so the usage sync must not charge the raise again
    assert row["data_limit"] == 60 * GB


def test_a_failed_read_refuses_the_disable(shared):
    _run(metering.enable(1, by=9))
    _use(5)
    FakeMarzban.fail_users = True
    with pytest.raises(metering.MeteringError):
        _run(metering.disable(1))
    assert metering.is_metered(1)
    with metering.db._connect() as conn:
        assert conn.execute("SELECT COUNT(*) FROM invoices").fetchone()[0] == 0


def test_re_enabling_starts_from_a_fresh_baseline(shared):
    _run(metering.enable(1, by=9))
    _use(5)
    _run(metering.disable(1))
    _use(100)  # used while off: paid the normal way, never billed here
    _run(metering.enable(1, by=9))
    assert metering.usage(1)["unsettled_bytes"] == 0
