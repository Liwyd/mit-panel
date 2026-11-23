"""The profit page's overview: buyers, days, methods, price bands, receivables."""

from contextlib import nullcontext
from datetime import datetime, timedelta, timezone

import pytest

from backend.bot import profit
from backend.bot.sales import TEHRAN, jalali_month_length, to_gregorian, to_jalali

# 2026-11-23 Tehran is 2 Azar 1405 (Azar has 30 days); Aban 1405 ended 2026-11-21.
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=TEHRAN)
AZAR = "1405-09"
ABAN = "1405-08"
MEHR = "1405-07"
UTC = timezone.utc


def add(ledger, method, amount, gb=0.0, username="alice", at=None):
    at = at or datetime(2026, 11, 23, 8, 0, tzinfo=UTC)
    with ledger._connect() as conn:
        conn.execute(
            "INSERT INTO sales (telegram_id, username, gb, amount, method, created_at) "
            "VALUES (1, ?, ?, ?, ?, ?)",
            (username, gb, amount, method, at.isoformat()),
        )


@pytest.fixture()
def settings(ledger, monkeypatch):
    values = {"cost_per_gb": 1000, "fixed_monthly_cost": 0, "monthly_revenue_target": 0}
    monkeypatch.setattr(profit.settings_store, "get_settings", lambda: dict(values))
    return values


def ov(month=None, months=12, now=NOW):
    return profit.overview(months, month, now=now)


def aban_day(day, hour=12):
    return datetime(*to_gregorian(1405, 8, day), hour, tzinfo=TEHRAN)


def azar_day(day, hour=12):
    return datetime(*to_gregorian(1405, 9, day), hour, tzinfo=TEHRAN)


def by_key(report, key):
    return next(m for m in report["months"] if m["key"] == key)


# --- calendar helpers ------------------------------------------------------

def test_gregorian_round_trip_and_month_lengths():
    assert to_gregorian(1405, 9, 1) == (2026, 11, 22)
    assert to_jalali(*to_gregorian(1405, 9, 2)) == (1405, 9, 2)
    assert [jalali_month_length(1405, m) for m in (1, 6, 7, 11)] == [31, 31, 30, 30]
    # Esfand has 30 days only in a leap year (1403 was one, 1404 was not).
    assert jalali_month_length(1403, 12) == 30
    assert jalali_month_length(1404, 12) == 29


# --- months, buyers, fixed cost --------------------------------------------

def test_active_new_and_lost_buyers(ledger, settings):
    add(ledger, "card", 100, gb=1, username="a", at=aban_day(5))
    add(ledger, "card", 100, gb=1, username="b", at=aban_day(6))
    add(ledger, "card", 100, gb=1, username="a", at=azar_day(1))
    add(ledger, "card", 100, gb=1, username="c", at=azar_day(2))
    # Not takings, or not a panel: none of these makes a buyer.
    add(ledger, "settlement", 100, username="d", at=azar_day(1))
    add(ledger, "grant", 0, gb=5, username="e", at=azar_day(1))
    add(ledger, "bf_discount", -10, username="f", at=azar_day(1))
    add(ledger, "invoice", 100, username=None, at=azar_day(1))

    report = ov()
    azar, aban = by_key(report, AZAR), by_key(report, ABAN)
    assert (aban["active_buyers"], aban["new_buyers"], aban["lost_buyers"]) == (2, 2, 0)
    # b bought in Aban and not in Azar; c is new in Azar.
    assert (azar["active_buyers"], azar["new_buyers"], azar["lost_buyers"]) == (2, 1, 1)


def test_a_returning_panel_is_not_new_again(ledger, settings):
    add(ledger, "card", 1, gb=1, username="a", at=aban_day(1))
    add(ledger, "card", 1, gb=1, username="a", at=azar_day(1))
    assert by_key(ov(), AZAR)["new_buyers"] == 0


def test_fixed_cost_and_net_profit_start_with_the_first_takings(ledger, settings):
    settings["fixed_monthly_cost"] = 300_000
    add(ledger, "card", 1_000_000, gb=500, at=aban_day(3))
    add(ledger, "card", 1_000_000, gb=500, at=azar_day(1))
    report = ov()
    azar = by_key(report, AZAR)
    assert azar["fixed_cost"] == 300_000
    assert azar["profit"] == 500_000 and azar["net_profit"] == 200_000
    assert by_key(report, ABAN)["fixed_cost"] == 300_000
    # Months before the first sale are not charged: that would be fake losses.
    assert by_key(report, MEHR)["fixed_cost"] == 0
    assert by_key(report, MEHR)["net_profit"] == 0


def test_net_profit_can_be_negative(ledger, settings):
    settings["fixed_monthly_cost"] = 900_000
    add(ledger, "card", 1_000_000, gb=500)
    assert by_key(ov(), AZAR)["net_profit"] == 1_000_000 - 500_000 - 900_000


def test_the_range_and_the_previous_month_comparison(ledger, settings):
    add(ledger, "card", 700, gb=1, at=aban_day(3))
    report = ov(months=6)
    assert [m["key"] for m in report["months"]][:2] == [AZAR, ABAN]
    assert len(report["months"]) == 6
    assert report["selected"]["previous"]["key"] == ABAN
    assert report["selected"]["previous"]["revenue"] == 700


def test_a_selected_month_outside_the_range_still_works(ledger, settings):
    add(ledger, "card", 700, gb=1, at=datetime(*to_gregorian(1405, 1, 5), 12, tzinfo=TEHRAN))
    selected = ov("1405-01", months=3)["selected"]
    assert selected["key"] == "1405-01" and selected["revenue"] == 700
    assert selected["forecast"] is None and selected["is_current"] is False


def test_a_bad_month_key_is_rejected(ledger, settings):
    for bad in ("1405-13", "1405-9", "x", "1405/09"):
        with pytest.raises(ValueError):
            ov(bad)


# --- daily -----------------------------------------------------------------

def test_daily_has_one_entry_per_day_and_flags_the_future(ledger, settings):
    add(ledger, "card", 500, gb=2, at=azar_day(1))
    add(ledger, "weekly", 300, gb=1, at=azar_day(2))
    add(ledger, "bf_discount", -50, at=azar_day(2))
    add(ledger, "settlement", 999, at=azar_day(2))
    daily = ov()["selected"]["daily"]
    assert len(daily) == 30
    assert [d["day"] for d in daily] == list(range(1, 31))
    assert daily[0]["revenue"] == 500 and daily[0]["gb_sold"] == 2
    # The waived discount reduces that day's revenue; the settlement is no revenue.
    assert daily[1]["revenue"] == 250 and daily[1]["gb_sold"] == 1
    assert daily[2]["revenue"] == 0 and daily[2]["gb_sold"] == 0
    assert [d["future"] for d in daily][:3] == [False, False, True]
    assert daily[0]["date"] == "2026-11-22"


def test_daily_month_lengths(ledger, settings):
    assert len(ov("1405-01")["selected"]["daily"]) == 31
    assert len(ov("1405-07")["selected"]["daily"]) == 30
    assert len(ov("1404-12")["selected"]["daily"]) == 29
    assert len(ov("1403-12")["selected"]["daily"]) == 30


def test_daily_follows_tehran_midnight(ledger, settings):
    # 20:29 UTC = 23:59 Tehran on 21 Nov: the last day of Aban.
    add(ledger, "card", 1, gb=1, at=datetime(2026, 11, 21, 20, 29, tzinfo=UTC))
    # 20:30 UTC = 00:00 Tehran on 22 Nov: day 1 of Azar.
    add(ledger, "card", 10, gb=1, at=datetime(2026, 11, 21, 20, 30, tzinfo=UTC))
    # 20:29 UTC on 22 Nov = 23:59 Tehran: still day 1.
    add(ledger, "card", 100, gb=1, at=datetime(2026, 11, 22, 20, 29, tzinfo=UTC))
    azar = ov()["selected"]["daily"]
    assert azar[0]["revenue"] == 110 and azar[1]["revenue"] == 0
    aban = ov(ABAN)["selected"]["daily"]
    assert aban[29]["revenue"] == 1 and aban[28]["revenue"] == 0


def test_a_past_month_has_no_future_days(ledger, settings):
    assert not any(d["future"] for d in ov(ABAN)["selected"]["daily"])


# --- forecast and target ---------------------------------------------------

def test_forecast_is_the_run_rate_of_the_month_so_far(ledger, settings):
    settings["monthly_revenue_target"] = 60_000_000
    settings["fixed_monthly_cost"] = 1_000_000
    add(ledger, "card", 2_000_000, gb=800, at=azar_day(1))
    add(ledger, "card", 1_000_000, gb=200, at=azar_day(2))
    f = ov()["selected"]["forecast"]
    # Today is day 2 of 30: 3M so far -> 3M / 2 * 30.
    assert (f["days_elapsed"], f["days_total"], f["days_left"]) == (2, 30, 28)
    assert f["month_to_date"] == 3_000_000
    assert f["projected_revenue"] == 45_000_000
    assert f["projected_cost"] == 15_000_000  # 1000 GB x 1000, scaled by 15
    assert f["projected_profit"] == 30_000_000
    assert f["projected_net_profit"] == 29_000_000
    assert f["target_progress"] == pytest.approx(0.05)
    assert f["projected_target_progress"] == pytest.approx(0.75)
    selected = ov()["selected"]
    assert selected["target"] == {"amount": 60_000_000, "progress": pytest.approx(0.05)}


def test_forecast_and_target_when_nothing_is_set(ledger, settings):
    selected = ov()["selected"]
    assert selected["forecast"]["projected_revenue"] == 0
    assert selected["forecast"]["target_progress"] is None
    assert selected["target"] is None
    assert ov(ABAN)["selected"]["forecast"] is None


# --- methods ---------------------------------------------------------------

def test_method_buckets_group_black_friday_and_other(ledger, settings):
    add(ledger, "card", 400, gb=1)
    add(ledger, "wallet", 100, gb=1)
    add(ledger, "weekly", 50, gb=1)
    add(ledger, "invoice", 20, gb=1)
    add(ledger, "shop", 10, gb=1)
    add(ledger, "bf_card", 300, gb=1)
    add(ledger, "bf_wallet", 100, gb=1)
    add(ledger, "mystery", 20, gb=1)
    add(ledger, "settlement", 5000)
    add(ledger, "bf_discount", -70)
    rows = {r["key"]: r for r in ov()["selected"]["by_method"]}
    assert rows["card"]["amount"] == 400 and rows["card"]["label"] == "کارت به کارت"
    assert rows["wallet"]["label"] == "کیف پول"
    assert rows["weekly"]["label"] == "اعتباری/پرداخت با تاخیر"
    assert rows["invoice"]["label"] == "فاکتور"
    assert rows["shop"]["label"] == "خرید پنل جدید"
    assert rows["black_friday"]["amount"] == 400 and rows["black_friday"]["count"] == 2
    assert rows["black_friday"]["label"] == "بلک‌فرایدی"
    assert rows["other"]["amount"] == 20 and rows["other"]["label"] == "سایر"
    assert "settlement" not in rows and "bf_discount" not in rows
    assert sum(r["share"] for r in rows.values()) == pytest.approx(1)
    assert rows["card"]["share"] == pytest.approx(400 / 1000)
    ordered = [r["amount"] for r in ov()["selected"]["by_method"]]
    assert ordered == sorted(ordered, reverse=True)


# --- price bands -----------------------------------------------------------

def test_price_band_edges_include_the_lower_edge(ledger, settings):
    # 1000 GB each: price = amount / 1000.
    cases = {
        "lt2000": [1_999_999, 1_000_000],
        "2000": [2_000_000, 2_399_999],
        "2400": [2_400_000, 2_699_999],
        "2700": [2_700_000, 2_999_999],
        "3000": [3_000_000, 4_000_000],
    }
    for amounts in cases.values():
        for amount in amounts:
            add(ledger, "card", amount, gb=1000)
    add(ledger, "invoice", 9_999_999, gb=0)  # no GB: no price, not in any band
    add(ledger, "settlement", 9_999_999, gb=1000)  # not takings
    bands = {b["key"]: b for b in ov()["selected"]["price_bands"]}
    assert list(bands) == list(cases)
    for key, amounts in cases.items():
        assert bands[key]["rows"] == 2, key
        assert bands[key]["gb"] == 2000
        assert bands[key]["revenue"] == sum(amounts)
    assert bands["2400"]["label"] == "۲٬۴۰۰ تا ۲٬۷۰۰"
    assert bands["lt2000"]["label"] == "زیر ۲٬۰۰۰"
    assert bands["3000"]["label"] == "بالای ۳٬۰۰۰"


def test_price_bands_are_all_present_when_empty(ledger, settings):
    bands = ov()["selected"]["price_bands"]
    assert len(bands) == 5 and all(b["gb"] == 0 and b["rows"] == 0 for b in bands)


# --- per panel, concentration ---------------------------------------------

def test_per_admin_has_margin_and_share_and_concentration(ledger, settings):
    for name, amount in [("a", 6_000_000), ("b", 2_000_000), ("c", 1_000_000), ("d", 500_000),
                         ("e", 300_000), ("f", 200_000)]:
        add(ledger, "card", amount, gb=amount / 2000, username=name)
    selected = ov()["selected"]
    rows = {r["username"]: r for r in selected["per_admin"]}
    assert rows["a"]["share"] == pytest.approx(0.6)
    assert rows["a"]["margin"] == pytest.approx(0.5)  # cost 1000/GB on a 2000/GB sale
    assert [r["username"] for r in selected["per_admin"]][0] == "a"
    c = selected["concentration"]
    assert c["top1_share"] == pytest.approx(0.6)
    assert c["top5_share"] == pytest.approx(0.98)
    assert c["top1_username"] == "a"


def test_concentration_with_no_revenue_is_null(ledger, settings):
    c = ov()["selected"]["concentration"]
    assert c["top1_share"] is None and c["top5_share"] is None and c["top1_username"] is None


def test_arpu_and_net_profit_per_gb(ledger, settings):
    settings["fixed_monthly_cost"] = 500_000
    add(ledger, "card", 2_000_000, gb=1000, username="a")
    add(ledger, "card", 1_000_000, gb=500, username="b")
    s = ov()["selected"]
    assert s["arpu"] == 1_500_000
    assert s["net_profit_per_gb"] == pytest.approx((3_000_000 - 1_500_000 - 500_000) / 1500)
    empty = ov(MEHR)["selected"]
    assert empty["arpu"] is None and empty["net_profit_per_gb"] is None


# --- break-even ------------------------------------------------------------

def test_break_even(ledger, settings):
    settings["fixed_monthly_cost"] = 1_000_000
    add(ledger, "card", 2_000_000, gb=800)  # 2500/GB, unit margin 1500
    s = ov()["selected"]
    assert s["break_even_gb"] == pytest.approx(1_000_000 / 1500, abs=0.01)
    assert s["break_even_reached"] is True  # 800 >= 666.67
    settings["fixed_monthly_cost"] = 3_000_000
    s = ov()["selected"]
    assert s["break_even_gb"] == 2000 and s["break_even_reached"] is False


def test_break_even_is_null_without_a_positive_margin(ledger, settings):
    settings["fixed_monthly_cost"] = 1_000_000
    add(ledger, "card", 800_000, gb=800)  # price 1000 = cost: nothing to divide by
    s = ov()["selected"]
    assert s["break_even_gb"] is None and s["break_even_reached"] is None
    # No priced GB at all.
    assert ov(MEHR)["selected"]["break_even_gb"] is None


# --- receivables -----------------------------------------------------------

def _debt(ledger, username, amount, late_days=None):
    ledger.add_debt(username, 1, amount)
    if late_days is not None:
        since = (NOW - timedelta(days=late_days, hours=1)).astimezone(UTC).isoformat()
        with ledger._connect() as conn:
            conn.execute("UPDATE debts SET overdue_since = ? WHERE username = ?", (since, username))


def _invoice(ledger, amount, due_days_ago=None):
    due = None if due_days_ago is None else (
        (NOW - timedelta(days=due_days_ago, hours=1)).astimezone(UTC).isoformat()
    )
    return ledger.create_invoice(telegram_id=1, amount=amount, description="x", due_at=due)


def test_receivables_totals_and_aging_buckets(ledger, settings):
    _debt(ledger, "current", 100)               # not late: due at the next settlement
    _debt(ledger, "today", 200, late_days=0)    # late by 1h: 0 whole days -> 1-7
    _debt(ledger, "seven", 300, late_days=7)    # 7 days 1h -> days_overdue 7 -> 1-7
    _debt(ledger, "eight", 400, late_days=8)    # -> 8-30
    _debt(ledger, "thirty", 500, late_days=30)  # -> 8-30
    _debt(ledger, "thirtyone", 600, late_days=31)  # -> over 30
    _debt(ledger, "paid", 0)                    # amount 0: not open
    _invoice(ledger, 1_000, None)               # open-ended: never late -> current
    _invoice(ledger, 2_000, due_days_ago=40)
    paid = _invoice(ledger, 5_000, due_days_ago=40)
    cancelled = _invoice(ledger, 7_000, due_days_ago=40)
    ledger.mark_invoice_paid(paid)
    ledger.cancel_invoice(cancelled)

    r = ov()["receivables"]
    assert (r["debts_total"], r["debts_count"]) == (2100, 6)
    assert (r["invoices_total"], r["invoices_count"]) == (3000, 2)
    assert r["total"] == 5100
    aging = {a["key"]: a for a in r["aging"]}
    assert [a["label"] for a in r["aging"]] == ["جاری", "۱ تا ۷ روز", "۸ تا ۳۰ روز", "بیش از ۳۰ روز"]
    assert (aging["current"]["amount"], aging["current"]["count"]) == (1100, 2)
    assert (aging["d1_7"]["amount"], aging["d1_7"]["count"]) == (500, 2)
    assert (aging["d8_30"]["amount"], aging["d8_30"]["count"]) == (900, 2)
    assert (aging["d30_plus"]["amount"], aging["d30_plus"]["count"]) == (2600, 2)
    assert sum(a["amount"] for a in r["aging"]) == r["total"]
    assert "cash_position" not in r


def test_wallet_balances_are_summed(ledger, settings):
    ledger.add_wallet_balance(1, 500_000)
    ledger.add_wallet_balance(2, 250_000)
    ledger.add_wallet_balance(3, 0)
    r = ov()["receivables"]
    assert r["wallet_total"] == 750_000 and r["wallet_count"] == 2


# --- consumption -----------------------------------------------------------

@pytest.fixture()
def panel_db(db_session, monkeypatch):
    monkeypatch.setattr(profit, "sessionLocal", lambda: nullcontext(db_session))
    return db_session


def _admin(session, name):
    from backend.db.model import Admins

    admin = Admins(username=name, hashed_password="x", panel="p")
    session.add(admin)
    session.commit()
    return admin.id


def _hour(session, admin_id, at, gib):
    from backend.db.model import AdminUsageHourly

    session.add(AdminUsageHourly(
        admin_id=admin_id, hour=at.astimezone(UTC).replace(tzinfo=None),
        used=int(gib * 1024 ** 3),
    ))
    session.commit()


def test_consumption_is_null_without_rows(ledger, settings, panel_db):
    assert ov()["selected"]["consumption"] is None


def test_consumption_is_null_when_the_table_is_missing(ledger, settings, monkeypatch):
    from sqlalchemy import create_engine
    from sqlalchemy.orm import sessionmaker
    from sqlalchemy.pool import StaticPool

    engine = create_engine("sqlite://", connect_args={"check_same_thread": False},
                           poolclass=StaticPool)
    monkeypatch.setattr(profit, "sessionLocal", sessionmaker(bind=engine))
    report = ov()
    assert report["selected"]["consumption"] is None
    assert report["selected"]["revenue"] == 0  # the rest of the section is intact


def test_consumption_sums_the_month_and_ranks_panels(ledger, settings, panel_db):
    add(ledger, "card", 1_000_000, gb=100)
    ids = {n: _admin(panel_db, n) for n in "abcdefg"}
    for i, name in enumerate("abcdefg"):
        _hour(panel_db, ids[name], azar_day(1, 10), 10 * (i + 1))
    # The hour starting 00:00 Tehran on 1 Azar is in; the last hour of Aban is not.
    _hour(panel_db, ids["a"], azar_day(1, 0), 1)
    _hour(panel_db, ids["a"], aban_day(30, 23), 500)
    c = ov()["selected"]["consumption"]
    assert c["used_gb"] == pytest.approx(10 * 28 + 1)
    assert c["use_to_sold"] == pytest.approx(281 / 100)
    assert len(c["top_panels"]) == 5
    assert c["top_panels"][0]["username"] == "g"
    assert c["top_panels"][0]["used_gb"] == pytest.approx(70)
    assert c["top_panels"][0]["share"] == pytest.approx(70 / 281)
    assert ov(ABAN)["selected"]["consumption"]["used_gb"] == pytest.approx(500)


def test_consumption_of_a_deleted_admin_is_still_counted(ledger, settings, panel_db):
    _hour(panel_db, 999, azar_day(1, 10), 3)
    c = ov()["selected"]["consumption"]
    assert c["top_panels"][0]["username"] == "#999"
    assert c["use_to_sold"] is None  # nothing sold to compare with


# --- resilience ------------------------------------------------------------

def test_a_failing_section_is_null_and_the_rest_survives(ledger, settings, monkeypatch):
    add(ledger, "card", 1_000_000, gb=500)

    def boom(*a, **k):
        raise RuntimeError("nope")

    monkeypatch.setattr(profit, "_by_method", boom)
    monkeypatch.setattr(profit, "receivables", boom)
    monkeypatch.setattr(profit, "black_friday_summary", boom)
    report = ov()
    assert report["selected"]["by_method"] is None
    assert report["receivables"] is None and report["black_friday"] is None
    assert report["selected"]["revenue"] == 1_000_000
    assert by_key(report, AZAR)["revenue"] == 1_000_000
    assert report["selected"]["daily"] is not None


def test_an_unreadable_ledger_nulls_the_ledger_sections(ledger, settings, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("ledger unreadable")

    monkeypatch.setattr(profit.db, "list_sales_since", boom)
    report = ov()
    assert report["months"] is None and report["selected"] is None
    assert report["settings"]["cost_per_gb"] == 1000
    assert report["receivables"] is not None


def test_settings_in_the_overview(ledger, settings):
    settings.update(fixed_monthly_cost=5, monthly_revenue_target=9)
    assert ov()["settings"] == {
        "cost_per_gb": 1000, "fixed_monthly_cost": 5, "monthly_revenue_target": 9,
    }


def test_unusable_money_settings_read_as_zero(ledger, monkeypatch):
    monkeypatch.setattr(
        profit.settings_store, "get_settings",
        lambda: {"fixed_monthly_cost": "x", "monthly_revenue_target": -5},
    )
    assert profit.fixed_monthly_cost() == 0 and profit.monthly_revenue_target() == 0


# --- settings validation and API -------------------------------------------

def test_new_settings_have_defaults_and_validation():
    from pydantic import ValidationError

    from backend.schema._input import SettingsInput
    from backend.utils import settings_store

    assert settings_store.DEFAULTS["fixed_monthly_cost"] == 0
    assert settings_store.DEFAULTS["monthly_revenue_target"] == 0
    assert SettingsInput(fixed_monthly_cost=0, monthly_revenue_target=5_000_000).fixed_monthly_cost == 0
    for field in ("fixed_monthly_cost", "monthly_revenue_target", "cost_per_gb"):
        with pytest.raises(ValidationError):
            SettingsInput(**{field: -1})


def test_overview_endpoint(ledger, settings, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.api.superadmin import routers
    from backend.app import app
    from backend.auth.auth import get_current_admin
    from backend.config import config

    client = TestClient(app, raise_server_exceptions=False)
    url = f"/{config.URLPATH}/superadmin/profit/overview"
    add(ledger, "card", 2_000_000, gb=1000)
    try:
        app.dependency_overrides[get_current_admin] = lambda: {"role": "admin", "username": "x"}
        denied = client.get(url)
        assert denied.status_code in (403, 500)
        assert "months" not in denied.text

        app.dependency_overrides[get_current_admin] = lambda: {"role": "superadmin"}
        body = client.get(url, params={"months": 3}).json()
        assert body["success"] is True
        data = body["data"]
        assert len(data["months"]) == 3
        assert set(data) >= {"settings", "months", "selected", "receivables", "black_friday"}
        assert client.get(url).json()["data"]["selected"]["key"] == profit.month_key_of(
            profit._wanted_months(1, None)[1][0]
        )

        picked = client.get(url, params={"month": "1405-08"}).json()
        assert picked["data"]["selected"]["key"] == "1405-08"

        for bad in ({"months": 0}, {"months": 25}, {"month": "1405-13"}, {"month": "abc"},
                    {"month": "1405-9"}):
            assert client.get(url, params=bad).status_code == 422, bad

        real = routers._build_profit_overview

        def boom(months, month):
            raise RuntimeError("ledger unreadable")

        monkeypatch.setattr(routers, "_build_profit_overview", boom)
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["success"] is False

        # The old endpoint still works.
        monkeypatch.setattr(routers, "_build_profit_overview", real)
        old = client.get(f"/{config.URLPATH}/superadmin/profit").json()
        assert old["success"] is True and "months" in old["data"]
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
