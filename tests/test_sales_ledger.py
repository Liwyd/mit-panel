"""The sales ledger: what was written down, and that it is seeded exactly once.

`backend.bot.db` opens its own SQLite file at a path derived from the live
installation, so the fixture points it at a temp file. Without that a test
would append rows to the panel's real data volume.
"""

from types import SimpleNamespace

import pytest

import backend.bot.db as bot_db


@pytest.fixture()
def ledger(tmp_path, monkeypatch):
    monkeypatch.setattr(
        bot_db, "bot_config", SimpleNamespace(sqlite_path=str(tmp_path / "bot.db"))
    )
    bot_db.init_db()
    return bot_db


def _clear_backfill_flag(db) -> None:
    """`init_db` already ran the backfill once (finding nothing), so the guard
    row exists. Tests that exercise it directly start from the un-seeded state."""
    with db._connect() as conn:
        conn.execute("DELETE FROM bot_settings WHERE key = 'sales_backfilled'")
        conn.execute("DELETE FROM sales")


def _approve_card(db, *, gb: float, amount: int) -> None:
    request_id = db.create_request(
        admin_telegram_id=111,
        admin_username="alice",
        requested_gb=gb,
        toman_amount=amount,
        receipt_path="/tmp/receipt.jpg",
    )
    db.mark_reviewed(request_id, status="approved", reviewed_by=1)


def test_init_db_is_idempotent(ledger):
    ledger.init_db()
    with ledger._connect() as conn:
        tables = {
            r["name"]
            for r in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")
        }
    assert "sales" in tables


def test_backfill_seeds_the_ledger_once(ledger):
    _clear_backfill_flag(ledger)
    _approve_card(ledger, gb=100, amount=50_000)
    _approve_card(ledger, gb=250, amount=125_000)

    assert ledger.backfill_sales_from_requests() == 2
    # Guard row is stamped, so a restart cannot seed the same receipts again.
    assert ledger.backfill_sales_from_requests() == 0

    sales = ledger.list_sales_since("1970-01-01T00:00:00+00:00")
    assert [(s.gb, s.amount, s.method) for s in sales] == [
        (100, 50_000, "card"),
        (250, 125_000, "card"),
    ]


def test_only_approved_card_receipts_are_seeded(ledger):
    _clear_backfill_flag(ledger)
    pending = ledger.create_request(
        admin_telegram_id=222,
        admin_username="bob",
        requested_gb=10,
        toman_amount=1_000,
        receipt_path="/tmp/receipt.jpg",
    )
    approved = ledger.create_request(
        admin_telegram_id=333,
        admin_username="carol",
        requested_gb=20,
        toman_amount=2_000,
        receipt_path="/tmp/receipt.jpg",
    )
    ledger.mark_reviewed(approved, status="approved", reviewed_by=1)
    # An approved invoice payment is money in, but not a traffic sale: the
    # backfill only ever seeded card receipts, because those are the only past
    # sales written down anywhere.
    invoice = ledger.create_request(
        admin_telegram_id=333,
        admin_username=None,
        requested_gb=0,
        toman_amount=2_000,
        receipt_path="/tmp/receipt.jpg",
        kind="invoice",
    )
    ledger.mark_reviewed(invoice, status="approved", reviewed_by=1)

    ledger.backfill_sales_from_requests()
    sales = ledger.list_sales_since("1970-01-01T00:00:00+00:00")
    assert len(sales) == 1
    assert sales[0].username == "carol"
    assert ledger.get_request(pending).status == "pending"


def test_settlements_are_recorded_but_stay_out_of_a_panels_history(ledger):
    ledger.record_sale(
        telegram_id=111, username="alice", gb=100, amount=50_000, method="weekly"
    )
    ledger.record_sale(
        telegram_id=111, username="alice", gb=0, amount=50_000, method="settlement"
    )

    history = ledger.list_sales_for("alice")
    assert [(s.gb, s.method) for s in history] == [(100, "weekly")]

    # The report reads everything since a cutoff and filters the payments out
    # itself, so the settlement is visible there.
    everything = ledger.list_sales_since("1970-01-01T00:00:00+00:00")
    assert {s.method for s in everything} == {"weekly", "settlement"}
    assert ledger.NOT_SALES == ("grant", "settlement", "wallet_charge")


def test_to_jalali_turns_nowruz_into_the_first_of_the_year(ledger):
    from datetime import date

    from backend.bot import sales

    assert sales.to_jalali(2026, 3, 21) == (1405, 1, 1)
    # 21 March 2026 is a Saturday, the first day of 1405.
    assert sales.format_day(date(2026, 3, 21)) == "1405/01/01 · شنبه"
    assert sales.day_of("2026-03-21T20:30:00+00:00") == date(2026, 3, 22)


def test_report_counts_takings_and_keeps_payments_beside_them(ledger):
    from backend.bot import sales, texts

    assert sales.report() == texts.SALES_EMPTY

    ledger.record_sale(telegram_id=111, username="alice", gb=100, amount=50_000, method="card")
    ledger.record_sale(telegram_id=111, username="alice", gb=0, amount=50_000, method="settlement")
    # Handing traffic over costs nothing, so it is history and not takings.
    ledger.record_sale(telegram_id=111, username="alice", gb=10, amount=0, method="grant")

    text = sales.report()
    assert texts.SALES_HEADER.strip() in text
    # One sale, not two: the grant and the settlement stay out of the count.
    assert "کارت 1" in text
    assert texts.SALES_SETTLED_TOTAL.format(total=50_000, count=1) in text


def test_history_lists_one_panel_and_omits_debt_payments(ledger):
    from backend.bot import sales, texts

    ledger.record_sale(telegram_id=111, username="alice", gb=100, amount=50_000, method="card")
    ledger.record_sale(telegram_id=111, username="alice", gb=0, amount=50_000, method="settlement")
    ledger.record_sale(telegram_id=111, username="bob", gb=10, amount=5_000, method="wallet")

    text = sales.history("alice")
    assert texts.HISTORY_HEADER.format(username="alice").strip() in text
    assert "+100 گیگ · کارت · 50,000 تومان" in text
    # A settlement moves no traffic, so it is not one of the charges.
    assert "تسویه‌ی هفتگی" not in text
    assert texts.HISTORY_FOOTER.format(gb=100, count=1) in text

    assert texts.HISTORY_EMPTY.format(username="nobody") == sales.history("nobody")
