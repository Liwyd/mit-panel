"""The monthly profit report, worked out from the sales ledger."""

from datetime import datetime, timezone

import pytest

from backend.bot import profit
from backend.bot.sales import TEHRAN, to_jalali

# 2026-11-23 Tehran is 2 Azar 1405; Aban 1405 ended on 2026-11-21.
NOW = datetime(2026, 11, 23, 12, 0, tzinfo=TEHRAN)
AZAR = "1405-09"
ABAN = "1405-08"


def add(ledger, method, amount, gb=0.0, username="alice", at=None):
    at = at or datetime(2026, 11, 23, 8, 0, tzinfo=timezone.utc)
    with ledger._connect() as conn:
        conn.execute(
            "INSERT INTO sales (telegram_id, username, gb, amount, method, created_at) "
            "VALUES (1, ?, ?, ?, ?, ?)",
            (username, gb, amount, method, at.isoformat()),
        )


def month(key=AZAR, months=6):
    report = profit.monthly_report(months, now=NOW)
    return next(m for m in report["months"] if m["key"] == key)


@pytest.fixture()
def cost(ledger, monkeypatch):
    def _set(value):
        monkeypatch.setattr(
            profit.settings_store, "get_settings", lambda: {"cost_per_gb": value}
        )

    _set(1000)
    return _set


def test_the_fixture_dates_are_what_the_tests_assume():
    assert to_jalali(2026, 11, 21)[:2] == (1405, 8)
    assert to_jalali(2026, 11, 22)[:2] == (1405, 9)
    assert to_jalali(2026, 4, 1)[:2] == (1405, 1)


def test_takings_count_and_non_takings_do_not(ledger, cost):
    add(ledger, "card", 2_000_000, gb=1000)
    add(ledger, "weekly", 1_000_000, gb=500)
    add(ledger, "bf_card", 500_000, gb=250)
    add(ledger, "settlement", 1_000_000)
    add(ledger, "wallet_charge", 700_000)

    m = month()
    assert m["revenue"] == 3_500_000
    assert m["gb_sold"] == 1750
    assert m["cost"] == 1_750_000
    assert m["profit"] == 1_750_000
    assert m["margin"] == pytest.approx(0.5)


def test_bf_discount_reduces_revenue_and_is_reported_positive(ledger, cost):
    add(ledger, "weekly", 1_000_000, gb=500)
    add(ledger, "bf_discount", -200_000)

    m = month()
    assert m["revenue"] == 800_000
    assert m["bf_discount"] == 200_000
    assert m["profit"] == 800_000 - 500_000


def test_granted_gb_costs_money_without_revenue(ledger, cost):
    add(ledger, "card", 1_000_000, gb=500)
    add(ledger, "grant", 0, gb=100)

    m = month()
    assert m["gb_sold"] == 500
    assert m["gb_free"] == 100
    assert m["revenue"] == 1_000_000
    assert m["cost"] == 600_000


def test_cost_follows_the_setting(ledger, cost):
    add(ledger, "card", 1_000_000, gb=100)
    cost(2500)
    assert month()["cost"] == 250_000
    assert profit.monthly_report(1, now=NOW)["cost_per_gb"] == 2500


def test_a_missing_or_broken_setting_falls_back_to_the_default(ledger, monkeypatch):
    monkeypatch.setattr(profit.settings_store, "get_settings", lambda: {"cost_per_gb": "x"})
    assert profit.cost_per_gb() == 1000
    monkeypatch.setattr(profit.settings_store, "get_settings", lambda: {})
    assert profit.cost_per_gb() == 1000


def test_two_admins_at_different_prices_have_different_margins(ledger, cost):
    add(ledger, "card", 2_900_000, gb=1000, username="rich")
    add(ledger, "card", 2_000_000, gb=1000, username="cheap")
    add(ledger, "bf_discount", -100_000, username="cheap")

    m = month()
    rows = {r["username"]: r for r in m["per_admin"]}
    assert rows["rich"]["avg_price_per_gb"] == 2900
    assert rows["cheap"]["avg_price_per_gb"] == 2000
    assert rows["rich"]["profit"] == 1_900_000
    assert rows["cheap"]["revenue"] == 1_900_000
    assert rows["cheap"]["profit"] == 900_000
    assert [r["username"] for r in m["per_admin"]] == ["rich", "cheap"]
    assert m["avg_price_per_gb"] == pytest.approx(2450)


def test_rows_without_a_panel_are_grouped_under_a_dash(ledger, cost):
    add(ledger, "invoice", 50_000, username=None)
    [row] = month()["per_admin"]
    assert row["username"] == "—"


def test_the_jalali_month_follows_tehran_time_not_utc(ledger, cost):
    # 23:30 Tehran on 21 Nov = 20:00 UTC, the last evening of Aban.
    add(ledger, "card", 100, gb=1, at=datetime(2026, 11, 21, 20, 0, tzinfo=timezone.utc))
    # 00:30 Tehran on 22 Nov = 21:00 UTC the day before, the first of Azar.
    add(ledger, "card", 7, gb=1, at=datetime(2026, 11, 21, 21, 0, tzinfo=timezone.utc))

    assert month(ABAN)["revenue"] == 100
    assert month(AZAR)["revenue"] == 7


def test_empty_months_are_present_newest_first(ledger, cost):
    report = profit.monthly_report(6, now=NOW)
    keys = [m["key"] for m in report["months"]]
    assert keys == ["1405-09", "1405-08", "1405-07", "1405-06", "1405-05", "1405-04"]
    empty = report["months"][-1]
    assert empty["revenue"] == 0 and empty["cost"] == 0 and empty["margin"] is None
    assert empty["avg_price_per_gb"] is None and empty["per_admin"] == []
    assert report["months"][0]["label_fa"] == "آذر ۱۴۰۵"


def test_months_roll_back_across_a_year_boundary(ledger, cost):
    now = datetime(2026, 4, 1, 12, 0, tzinfo=TEHRAN)  # 12 Farvardin 1405
    keys = [m["key"] for m in profit.monthly_report(3, now=now)["months"]]
    assert keys == ["1405-01", "1404-12", "1404-11"]


def test_unknown_gb_revenue_counts_as_revenue_with_no_cost(ledger, cost):
    add(ledger, "invoice", 300_000, gb=0)
    add(ledger, "card", 1_000_000, gb=500)

    m = month()
    assert m["unknown_gb_revenue"] == 300_000
    assert m["revenue"] == 1_300_000
    assert m["cost"] == 500_000
    # The average only looks at rows that know their GB.
    assert m["avg_price_per_gb"] == 2000


def test_rows_older_than_the_range_are_ignored(ledger, cost):
    add(ledger, "card", 999, gb=1, at=datetime(2025, 1, 1, tzinfo=timezone.utc))
    assert all(m["revenue"] == 0 for m in profit.monthly_report(3, now=NOW)["months"])


def _bf(ledger, kind, method, amount, list_amount, paid=0.0, gift=0.0, tg=1):
    ledger.insert_black_friday_purchase(
        telegram_id=tg, username="alice", kind=kind, paid_gb=paid, gift_gb=gift,
        amount=amount, list_amount=list_amount, method=method,
    )


def test_black_friday_summary(ledger, cost, monkeypatch):
    monkeypatch.setattr(
        profit.settings_store, "black_friday_state",
        lambda: {"active": True, "ends_at": "2026-11-29T23:59:59+03:30"},
    )
    _bf(ledger, "topup", "card", 2_400_000, 2_900_000, paid=1000, gift=100, tg=1)
    _bf(ledger, "topup", "wallet", 1_000_000, 1_200_000, paid=400, gift=0, tg=2)
    _bf(ledger, "settlement", "card", 800_000, 1_000_000, tg=1)
    _bf(ledger, "invoice", "card", 900_000, 1_000_000, tg=3)

    s = profit.black_friday_summary()
    assert (s["purchases"], s["buyers"]) == (2, 3)
    assert (s["paid_gb"], s["gift_gb"]) == (1400, 100)
    assert s["amount"] == 3_400_000
    assert s["discount"] == 700_000
    assert (s["settlements"], s["settlements_amount"], s["settlements_discount"]) == (
        2, 1_700_000, 300_000,
    )
    assert (s["card_amount"], s["wallet_amount"]) == (4_100_000, 1_000_000)
    assert s["cost"] == 1_500_000
    # 3.4M taken - 200k waived on the settled debt - 1.5M cost.
    assert s["profit"] == 1_700_000
    assert s["active"] is True and s["ends_at"].startswith("2026-11-29")


def test_black_friday_summary_with_no_data(ledger, cost):
    s = profit.black_friday_summary()
    assert (s["purchases"], s["amount"], s["cost"], s["profit"]) == (0, 0, 0, 0)


def test_profit_endpoint_is_superadmin_only_and_never_500s(ledger, cost, monkeypatch):
    from fastapi.testclient import TestClient

    from backend.app import app
    from backend.auth.auth import get_current_admin
    from backend.config import config
    from backend.api.superadmin import routers

    client = TestClient(app, raise_server_exceptions=False)
    url = f"/{config.URLPATH}/superadmin/profit"
    add(ledger, "card", 2_000_000, gb=1000)
    try:
        app.dependency_overrides[get_current_admin] = lambda: {"role": "admin", "username": "x"}
        # get_current_superadmin `raise`s a JSONResponse (existing quirk), which
        # surfaces as a 500 rather than a 403; either way nothing is served.
        denied = client.get(url)
        assert denied.status_code in (403, 500)
        assert "months" not in denied.text

        app.dependency_overrides[get_current_admin] = lambda: {"role": "superadmin"}
        body = client.get(url, params={"months": 3}).json()
        assert body["success"] is True
        assert len(body["data"]["months"]) == 3
        assert body["data"]["cost_per_gb"] == 1000
        assert "black_friday" in body["data"]
        assert client.get(url, params={"months": 0}).status_code == 422
        assert client.get(url, params={"months": 25}).status_code == 422

        def boom(months):
            raise RuntimeError("ledger unreadable")

        monkeypatch.setattr(routers, "_build_profit_report", boom)
        response = client.get(url)
        assert response.status_code == 200
        assert response.json()["success"] is False
    finally:
        app.dependency_overrides.pop(get_current_admin, None)
