"""The rules that decide what a reseller owes.

Each of these branches is money: getting them wrong either bills someone for
users they already had or lets out-of-band users go unpaid.
"""

from datetime import datetime
from zoneinfo import ZoneInfo

from backend.bot.usage_sync import (
    LiveUser,
    invoice_amount,
    new_debt,
    plan_charge,
    should_run,
    to_live_map,
)

TEHRAN = ZoneInfo("Asia/Tehran")
GB = 1024**3


def live(name, limit):
    return {name: LiveUser(name, limit)}


def test_first_run_adopts_everything_without_charging():
    plan = plan_charge(live("a", 10 * GB), ledger={})

    assert plan.charges == []
    assert [u.username for u in plan.adopted] == ["a"]


def test_a_user_the_ledger_never_saw_is_charged_once():
    plan = plan_charge(live("a", 10 * GB), ledger={"other": 5 * GB})

    assert [(c.username, c.amount) for c in plan.charges] == [("a", 10 * GB)]


def test_a_raised_limit_is_charged_by_the_difference_only():
    plan = plan_charge(live("a", 30 * GB), ledger={"a": 20 * GB})

    assert [c.amount for c in plan.charges] == [10 * GB]


def test_a_lowered_limit_is_recorded_and_refunds_nothing():
    plan = plan_charge(live("a", 5 * GB), ledger={"a": 20 * GB})

    assert plan.charges == []
    assert [u.data_limit for u in plan.adopted] == [5 * GB]


def test_a_deleted_user_is_forgotten_without_a_refund():
    plan = plan_charge(live("b", 5 * GB), ledger={"a": 20 * GB, "b": 5 * GB})

    assert plan.charges == []
    assert plan.pruned == ["a"]


def test_a_panel_reporting_no_users_at_all_is_left_alone():
    """A read that came back empty must not look like every user was deleted,
    or one bad sweep would wipe the ledger and the debt it was tracking."""
    plan = plan_charge({}, ledger={"a": 20 * GB})

    assert plan.skip_reason is not None
    assert plan.pruned == []


def test_zero_limit_users_are_record_but_not_priced():
    plan = plan_charge(live("a", 0), ledger={"b": 5 * GB})

    assert plan.charges == []
    assert [u.username for u in plan.adopted] == ["a"]


def test_only_traffic_that_dipped_below_zero_is_owed():
    assert new_debt(before=50 * GB, after=-50 * GB) == 50 * GB
    assert new_debt(before=0, after=-100 * GB) == 100 * GB
    # Started positive, still positive: nothing new to invoice.
    assert new_debt(before=200 * GB, after=100 * GB) == 0


def test_invoice_amount_rounds_to_whole_toman():
    assert invoice_amount(100 * GB, 50_000) == 5_000_000
    assert invoice_amount(0, 50_000) == 0


def test_users_without_an_owner_are_dropped_by_to_live_map():
    assert list(to_live_map([{"username": ""}, {"username": "a"}])) == ["a"]


def test_sweep_only_runs_on_its_slots():
    at_three = datetime(2026, 9, 27, 3, 1, tzinfo=TEHRAN)
    at_four = datetime(2026, 9, 27, 4, 1, tzinfo=TEHRAN)

    assert should_run(at_three, stamp=None, retry_after=None) is True
    assert should_run(at_four, stamp=None, retry_after=None) is False
    assert should_run(at_three, stamp="2026-09-27@3", retry_after=None) is False
    # A failure sets a future retry time; until it passes the slot stays held.
    backoff = datetime(2026, 9, 27, 3, 30, tzinfo=TEHRAN).isoformat()
    assert should_run(at_three, stamp=None, retry_after=backoff) is False
