"""The usage recorder: what feeds the Analytics usage charts.

Deliberately read-only — it must never charge, refund or edit a balance, so a
bug in here can only cost chart accuracy. These tests pin the properties that
matter for a live panel:

* the first reading of an admin is a **baseline**, not traffic (otherwise
  everything ever consumed would land in one hour on day one),
* growth is booked, shrinkage is not,
* a user nobody owns (made straight in Marzban, `admin: null`) is dropped,
* the one-off sales backfill marks itself done and never runs twice.
"""

from datetime import datetime, timedelta

import pytest

from backend.auth.hash import hash_password
from backend.db import crud
from backend.db.model import Admins, AdminTrafficLog, AdminUsageHourly
from backend.services.marzban import usage_recorder
from backend.utils import analytics

NOW = datetime(2026, 5, 11, 9, 30)


@pytest.fixture(autouse=True)
def empty_baseline(monkeypatch):
    """`_totals` is module state carried across passes; start every test clean."""
    monkeypatch.setattr(usage_recorder, "_totals", {})


@pytest.fixture()
def owner(db_session, marzban_panel):
    db_session.add(
        Admins(
            username="nima",
            hashed_password=hash_password("pw"),
            panel=marzban_panel.name,
            is_active=True,
            traffic=100,
        )
    )
    db_session.commit()
    return marzban_panel.name


_UNSET = object()


def _row(used: int, *, owner: str = "nima", limit: int = 100, created=_UNSET):
    return {
        "owner": owner,
        "used": used,
        "limit": limit,
        # `created=None` means "Marzban didn't say", which must stay None.
        "created": NOW - timedelta(days=1) if created is _UNSET else created,
    }


# --- what gets read ---------------------------------------------------------

def test_slim_keeps_only_what_recording_needs():
    slim = usage_recorder._slim(
        {
            "admin": {"username": "nima"},
            "used_traffic": 4_000,
            "data_limit": 10_000,
            "created_at": "2026-05-01T10:00:00Z",
            "proxies": {"vless": {"id": "..." * 10}},
        }
    )

    assert slim == {
        "owner": "nima",
        "used": 4_000,
        "limit": 10_000,
        "created": datetime(2026, 5, 1, 10, 0),
    }


def test_slim_drops_users_nobody_can_be_charged_for():
    # `admin: null` belongs to the panel itself.
    assert usage_recorder._slim({"admin": None, "used_traffic": 5}) is None
    # Traffic we can't parse must not be read as zero and hide real growth.
    assert (
        usage_recorder._slim({"admin": {"username": "nima"}, "used_traffic": "junk"})
        is None
    )
    # A negative counter is nonsense, not a refund.
    slim = usage_recorder._slim(
        {"admin": {"username": "nima"}, "used_traffic": -9, "data_limit": -1}
    )
    assert slim["used"] == 0
    assert slim["limit"] == 0


# --- booking ----------------------------------------------------------------

def test_the_first_reading_is_a_baseline_not_a_days_usage(db_session, owner):
    usage_recorder._record_panel(owner, [_row(50_000)], NOW)

    db_session.expire_all()
    assert db_session.query(AdminUsageHourly).count() == 0
    # ...but it is the moment the sales log can be backfilled.
    assert db_session.query(AdminTrafficLog).filter_by(kind="backfill").count() == 2


def test_growth_since_the_last_reading_is_booked(db_session, owner):
    usage_recorder._record_panel(owner, [_row(50_000)], NOW)
    usage_recorder._record_panel(owner, [_row(62_000)], NOW + timedelta(minutes=5))

    db_session.expire_all()
    row = db_session.query(AdminUsageHourly).one()
    assert row.used == 12_000
    assert row.hour == analytics.hour_start(NOW + timedelta(minutes=5))


def test_a_fall_is_never_booked_as_negative_usage(db_session, owner):
    """A deleted user or a usage reset shrinks the total.

    The baseline has to come down with it, or the next growth would be booked
    twice — once for what the deletion already freed.
    """
    usage_recorder._record_panel(owner, [_row(50_000)], NOW)
    usage_recorder._record_panel(owner, [_row(1_000)], NOW + timedelta(minutes=5))
    usage_recorder._record_panel(owner, [_row(4_000)], NOW + timedelta(minutes=10))

    db_session.expire_all()
    assert db_session.query(AdminUsageHourly).one().used == 3_000


def test_users_of_another_panels_admin_are_ignored(db_session, owner):
    """Same guard the billing sync uses: a name belonging to a different
    panel's admin is nobody's usage here."""
    usage_recorder._record_panel("some-other-panel", [_row(50_000)], NOW)

    db_session.expire_all()
    assert db_session.query(AdminUsageHourly).count() == 0
    assert db_session.query(AdminTrafficLog).count() == 0


def test_an_admin_who_no_longer_exists_is_skipped(db_session, owner):
    usage_recorder._record_panel(owner, [_row(1, owner="deleted-reseller")], NOW)

    db_session.expire_all()
    assert db_session.query(AdminUsageHourly).count() == 0


def test_growth_is_summed_over_all_of_that_owners_users(db_session, owner):
    usage_recorder._record_panel(
        owner,
        [_row(10_000), _row(20_000), _row(5_000)],
        NOW,
    )
    usage_recorder._record_panel(
        owner,
        [_row(12_000), _row(25_000), _row(5_000)],
        NOW + timedelta(minutes=5),
    )

    db_session.expire_all()
    assert db_session.query(AdminUsageHourly).one().used == 7_000


# --- the sales backfill -----------------------------------------------------

def test_the_backfill_reads_the_users_own_creation_dates(db_session, owner):
    """Sales from before the log existed, at what they actually cost."""
    created = NOW - timedelta(days=2)
    usage_recorder._record_panel(owner, [_row(100, created=created)], NOW)

    db_session.expire_all()
    sales = [
        r
        for r in db_session.query(AdminTrafficLog).order_by(AdminTrafficLog.id)
        if r.kind == "backfill" and r.amount
    ]
    assert [(r.amount, r.created_at) for r in sales] == [(100, created)]


def test_the_backfill_never_runs_twice(db_session, owner):
    usage_recorder._record_panel(owner, [_row(100)], NOW)
    # A later pass, with users created since: none of it is backfilled again.
    usage_recorder._record_panel(
        owner, [_row(100, created=NOW - timedelta(hours=1))], NOW + timedelta(minutes=5)
    )

    db_session.expire_all()
    markers = db_session.query(AdminTrafficLog).filter_by(kind="backfill").all()
    assert len([m for m in markers if m.amount == 0]) == 1  # exactly one marker
    assert len([m for m in markers if m.amount]) == 1  # only the first pass's user


def test_a_user_made_after_the_log_started_is_not_backfilled(db_session, owner):
    """`until` is capped by the first real sale, so users created after it are
    regular sales, not history."""
    first_sale = NOW - timedelta(days=1)
    db_session.add(
        AdminTrafficLog(
            admin_id=crud.get_admin_by_username(db_session, "nima").id,
            amount=10,
            kind="charge",
            created_at=first_sale,
        )
    )
    db_session.commit()

    # Created after that sale: outside the backfill window.
    usage_recorder._record_panel(
        owner, [_row(100, created=NOW - timedelta(hours=2))], NOW
    )

    db_session.expire_all()
    backfilled = [
        r.amount
        for r in db_session.query(AdminTrafficLog).filter_by(kind="backfill")
        if r.amount
    ]
    assert backfilled == []


def test_a_user_without_a_creation_date_is_left_out(db_session, owner):
    usage_recorder._record_panel(owner, [_row(100, created=None)], NOW)

    db_session.expire_all()
    assert not [
        r.amount
        for r in db_session.query(AdminTrafficLog).filter_by(kind="backfill")
        if r.amount
    ]


def test_a_zero_limit_user_is_not_a_sale(db_session, owner):
    usage_recorder._record_panel(owner, [_row(0, limit=0)], NOW)

    db_session.expire_all()
    assert not [
        r.amount
        for r in db_session.query(AdminTrafficLog).filter_by(kind="backfill")
        if r.amount
    ]


def test_a_failed_pass_leaves_the_baseline_where_it_was(db_session, owner):
    """The baselines only move once the commit lands.

    Otherwise a rejected write would be remembered as done and the chart would
    quietly keep a hole for that pass.
    """
    usage_recorder._record_panel(owner, [_row(50_000)], NOW)

    from backend.db import engin

    real = engin.sessionLocal

    def refusing():
        session = real()

        def boom():
            raise RuntimeError("database is busy")

        session.commit = boom  # type: ignore[method-assign]
        return session

    import backend.services.marzban.usage_recorder as recorder

    original = recorder.engin.sessionLocal
    recorder.engin.sessionLocal = refusing
    try:
        recorder._record_panel(owner, [_row(60_000)], NOW + timedelta(minutes=5))
    finally:
        recorder.engin.sessionLocal = original

    db_session.expire_all()
    # Nothing was booked for the failed pass...
    assert db_session.query(AdminUsageHourly).count() == 0

    # ...so the retry books the whole gap instead of only the next increment.
    usage_recorder._record_panel(owner, [_row(75_000)], NOW + timedelta(minutes=10))
    db_session.expire_all()
    assert db_session.query(AdminUsageHourly).one().used == 25_000
