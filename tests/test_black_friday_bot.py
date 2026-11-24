"""Black Friday in the bot: pricing, who may buy, settling debt at the event
rate, the approval paths and the places the event touches existing behaviour.

`backend.bot.db` is pointed at a temp SQLite file by the `ledger` fixture, and
the panel's own database is an in-memory one (see conftest), so nothing here
reaches live data. The event switch is patched on `black_friday.is_active`, the
single function every other module asks.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.bot import (
    approvals,
    billing,
    black_friday,
    db,
    forecast,
    keyboards,
    nav,
    panel_client as panel_client_module,
    sales,
    texts,
)
from backend.bot.panel_client import PanelClientError

# The real grant, kept before any fixture swaps it for a mock.
_real_topup = panel_client_module.topup
from backend.bot.routers import black_friday as bf_router
from backend.db.model import Admins

GB = 1024**3
ALICE = 111
BOB = 222


class FakeBot:
    def __init__(self):
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


@pytest.fixture()
def event(monkeypatch):
    """Switch the event on or off."""

    def _set(active: bool):
        monkeypatch.setattr(black_friday, "is_active", lambda: active)

    _set(True)
    return _set


@pytest.fixture()
def admin(db_session):
    def make(username="alice", telegram_id=ALICE, traffic=100 * GB):
        row = Admins(
            username=username, hashed_password="x", telegram_id=telegram_id,
            panel="touch", is_active=True, traffic=traffic,
        )
        db_session.add(row)
        db_session.commit()
        return row

    return make


@pytest.fixture()
def granted(monkeypatch):
    """Replace the panel grant; the mock records what would have been credited."""
    mock = AsyncMock(return_value={"new_traffic_bytes": 500 * GB})
    monkeypatch.setattr(panel_client_module, "topup", mock)
    return mock


def sql(ledger, query, params=()):
    with ledger._connect() as conn:
        return [dict(r) for r in conn.execute(query, params).fetchall()]


def ledger_rows(ledger, method):
    return sql(ledger, "SELECT * FROM sales WHERE method = ?", (method,))


def priced(ledger, global_price=None, special=None, username="alice"):
    if global_price is not None:
        ledger.set_setting("price_per_gb", str(global_price))
    if special is not None:
        ledger.set_admin_price(username, special)


# ---- is_active ---------------------------------------------------------------------

def test_is_active_never_raises(monkeypatch):
    import backend.utils.settings_store as store

    def boom(*args, **kwargs):
        raise RuntimeError("settings unreadable")

    monkeypatch.setattr(store, "black_friday_state", boom)
    assert black_friday.is_active() is False


def test_is_active_follows_the_theme_state(monkeypatch):
    import backend.utils.settings_store as store

    monkeypatch.setattr(store, "black_friday_state", lambda: {"active": True, "ends_at": None})
    assert black_friday.is_active() is True
    monkeypatch.setattr(store, "black_friday_state", lambda: {"active": False, "ends_at": None})
    assert black_friday.is_active() is False


# ---- pricing and gift eligibility ------------------------------------------------------

@pytest.mark.parametrize(
    "price, expected_price, eligible",
    [
        (2900, 2400, True),
        (2400.5, 2400, True),
        (2400, 2400, False),
        (2000, 2000, False),
    ],
)
def test_bf_price_and_gift_eligibility(ledger, price, expected_price, eligible):
    priced(ledger, special=price)
    assert black_friday.bf_price("alice") == expected_price
    assert black_friday.gift_eligible("alice") is eligible


def test_an_unset_price_buys_at_the_public_rate_with_no_gift(ledger):
    assert ledger.get_effective_price("alice") == 0
    assert black_friday.bf_price("alice") == 2400
    assert black_friday.gift_eligible("alice") is False


def test_a_package_quote_for_an_eligible_admin(ledger):
    priced(ledger, global_price=2900)
    quote = black_friday.package_quote("alice", 1000)
    assert quote.paid_gb == 1000 and quote.gift_gb == 260
    assert quote.total == 2_400_000
    assert quote.granted_gb == 1260
    assert quote.list_total == 2_900_000
    assert quote.saving == 500_000


def test_every_package_gifts_what_the_event_promises(ledger):
    priced(ledger, global_price=3000)
    got = {
        int(q.paid_gb): (int(q.gift_gb), q.total)
        for q in (black_friday.package_quote("alice", p) for p, _ in black_friday.PACKAGES)
    }
    assert got == {
        1000: (260, 2_400_000),
        2000: (360, 4_800_000),
        3000: (460, 7_200_000),
        5000: (560, 12_000_000),
    }


def test_a_special_price_at_or_below_the_rate_pays_it_and_gets_no_gift(ledger):
    priced(ledger, special=2200)
    quote = black_friday.package_quote("alice", 2000)
    assert quote.gift_gb == 0
    assert quote.total == 4_400_000
    assert quote.saving == 0  # no saving is claimed when the own price is lower


def test_an_unknown_package_is_refused(ledger):
    priced(ledger, global_price=2900)
    assert black_friday.package_quote("alice", 1500) is None
    assert black_friday.package_quote("alice", 0) is None


@pytest.mark.parametrize("gb, ok", [(199, False), (200, True), (6000, True), (6001, False)])
def test_custom_amount_bounds(ledger, gb, ok):
    priced(ledger, global_price=2900)
    quote = black_friday.custom_quote("alice", gb)
    assert (quote is not None) is ok


def test_a_custom_amount_never_gets_a_gift(ledger):
    priced(ledger, global_price=2900)
    quote = black_friday.custom_quote("alice", 300)
    assert quote.gift_gb == 0
    assert quote.total == 720_000
    assert quote.granted_gb == 300


# ---- who may buy --------------------------------------------------------------------------

def test_nobody_owing_anything_is_blocked_without_bills(ledger):
    assert black_friday.has_open_bills(ALICE) is False


def test_a_pending_invoice_blocks_buying(ledger):
    ledger.create_invoice(telegram_id=ALICE, amount=5000, description="x", due_at=None)
    assert black_friday.has_open_bills(ALICE) is True
    assert black_friday.has_open_bills(BOB) is False


def test_a_weekly_debt_blocks_buying(ledger):
    ledger.add_debt("alice", ALICE, 1000)
    assert black_friday.has_open_bills(ALICE) is True


def test_a_paid_invoice_no_longer_blocks(ledger):
    invoice = ledger.create_invoice(telegram_id=ALICE, amount=5000, description="x", due_at=None)
    ledger.mark_invoice_paid(invoice)
    assert black_friday.has_open_bills(ALICE) is False


# ---- settling debt at the event rate -----------------------------------------------------------

def test_debt_quote_rounds_the_discounted_amount_up(ledger):
    priced(ledger, special=2800)
    ledger.add_debt("alice", ALICE, 1000)
    # 1000 * 2400 / 2800 = 857.14...
    assert black_friday.debt_quote("alice") == (1000, 858, 142)


def test_debt_quote_is_exact_when_the_ratio_divides_evenly(ledger):
    priced(ledger, special=3000)
    ledger.add_debt("alice", ALICE, 1_000_000)
    assert black_friday.debt_quote("alice") == (1_000_000, 800_000, 200_000)


def test_debt_quote_is_unchanged_at_or_below_the_rate(ledger):
    priced(ledger, special=2400)
    ledger.add_debt("alice", ALICE, 1_000_000)
    assert black_friday.debt_quote("alice") == (1_000_000, 1_000_000, 0)
    priced(ledger, special=2000)
    assert black_friday.debt_quote("alice") == (1_000_000, 1_000_000, 0)


def test_debt_quote_with_no_debt(ledger):
    assert black_friday.debt_quote("alice") == (0, 0, 0)


def test_a_traffic_invoice_is_priced_at_the_event_rate(ledger):
    priced(ledger, special=2900)
    invoice = ledger.create_invoice(
        telegram_id=ALICE, amount=2_900_000, description="x", due_at=None,
        admin_username="alice", traffic_gb=1000,
    )
    original, discounted, saving = black_friday.invoice_quote(ledger.get_invoice(invoice))
    assert (original, discounted, saving) == (2_900_000, 2_400_000, 500_000)


def test_a_traffic_invoice_is_never_raised_above_its_amount(ledger):
    priced(ledger, special=2900)
    invoice = ledger.create_invoice(
        telegram_id=ALICE, amount=1_000_000, description="x", due_at=None,
        admin_username="alice", traffic_gb=1000,
    )
    assert black_friday.invoice_quote(ledger.get_invoice(invoice)) == (1_000_000, 1_000_000, 0)


def test_manual_and_maintenance_invoices_are_not_discounted(ledger):
    priced(ledger, special=2900)
    manual = ledger.create_invoice(telegram_id=ALICE, amount=50_000, description="m", due_at=None)
    maintenance = ledger.create_invoice(
        telegram_id=ALICE, amount=70_000, description="maint", due_at=None, admin_username="alice"
    )
    assert black_friday.invoice_quote(ledger.get_invoice(manual)) == (50_000, 50_000, 0)
    assert black_friday.invoice_quote(ledger.get_invoice(maintenance)) == (70_000, 70_000, 0)


# ---- wallet auto-drain -----------------------------------------------------------------------------

def test_drain_is_unchanged_when_the_event_is_off(ledger, event):
    event(False)
    priced(ledger, special=3000)
    ledger.add_debt("alice", ALICE, 1_000_000)
    ledger.add_wallet_balance(ALICE, 900_000)

    results = billing.apply_wallet_to_debts(ALICE)

    assert results == [{"username": "alice", "paid": 900_000, "remaining": 100_000}]
    assert ledger.get_wallet_balance(ALICE) == 0
    assert [r["amount"] for r in ledger_rows(ledger, "settlement")] == [900_000]
    assert ledger_rows(ledger, "bf_discount") == []
    assert ledger.list_black_friday_purchases() == []


def test_drain_clears_a_debt_at_the_event_rate(ledger, event):
    priced(ledger, special=3000)
    ledger.add_debt("alice", ALICE, 1_000_000)
    ledger.add_wallet_balance(ALICE, 1_000_000)

    results = billing.apply_wallet_to_debts(ALICE)

    assert results == [{"username": "alice", "paid": 800_000, "remaining": 0}]
    assert ledger.get_debt("alice") == 0
    assert ledger.get_wallet_balance(ALICE) == 200_000
    assert [r["amount"] for r in ledger_rows(ledger, "settlement")] == [800_000]
    assert [r["amount"] for r in ledger_rows(ledger, "bf_discount")] == [-200_000]
    [row] = ledger.list_black_friday_purchases()
    assert (row.kind, row.method, row.amount, row.list_amount) == ("settlement", "wallet", 800_000, 1_000_000)


def test_a_partial_drain_cancels_the_matching_share_of_the_debt(ledger, event):
    priced(ledger, special=3000)
    ledger.add_debt("alice", ALICE, 1_000_000)
    ledger.add_wallet_balance(ALICE, 400_000)

    results = billing.apply_wallet_to_debts(ALICE)

    # 400,000 at the event rate retires 400,000 * 3000 / 2400 = 500,000.
    assert results == [{"username": "alice", "paid": 400_000, "remaining": 500_000}]
    assert ledger.get_debt("alice") == 500_000
    assert ledger.get_wallet_balance(ALICE) == 0
    assert [r["amount"] for r in ledger_rows(ledger, "bf_discount")] == [-100_000]


def test_drain_during_the_event_leaves_cheap_debts_alone(ledger, event):
    priced(ledger, special=2200)
    ledger.add_debt("alice", ALICE, 1_000_000)
    ledger.add_wallet_balance(ALICE, 600_000)

    results = billing.apply_wallet_to_debts(ALICE)

    assert results == [{"username": "alice", "paid": 600_000, "remaining": 400_000}]
    assert ledger_rows(ledger, "bf_discount") == []


# ---- the ledger ---------------------------------------------------------------------------------------

def test_the_discount_is_not_a_sale(ledger):
    assert db.BF_DISCOUNT_METHOD in db.NOT_SALES
    assert db.BF_CARD_METHOD not in db.NOT_SALES
    assert db.BF_WALLET_METHOD not in db.NOT_SALES
    assert {"bf_card", "bf_wallet", "bf_discount"} <= set(texts.SALES_METHOD_LABELS)


def test_the_weekly_report_ignores_the_discount_but_counts_event_sales(ledger):
    ledger.record_sale(telegram_id=ALICE, username="alice", gb=1260, amount=2_400_000, method="bf_card")
    ledger.record_sale(telegram_id=ALICE, username="alice", gb=0, amount=-100_000, method="bf_discount")
    report = sales.report()
    assert "2,400,000" in report
    assert "-100,000" not in report


def test_a_panel_history_does_not_list_the_discount(ledger):
    ledger.record_sale(telegram_id=ALICE, username="alice", gb=1260, amount=2_400_000, method="bf_card")
    ledger.record_sale(telegram_id=ALICE, username="alice", gb=0, amount=-100_000, method="bf_discount")
    assert [s.method for s in ledger.list_sales_for("alice")] == ["bf_card"]


def test_init_db_is_idempotent_with_the_new_table(ledger):
    ledger.init_db()
    ledger.init_db()
    assert ledger.list_black_friday_purchases() == []
    ledger.insert_black_friday_purchase(
        telegram_id=ALICE, username="alice", kind="topup", paid_gb=1000, gift_gb=260,
        amount=2_400_000, list_amount=2_900_000, method="card",
    )
    assert len(ledger.list_black_friday_purchases()) == 1
    assert ledger.list_black_friday_purchases(since="2999-01-01T00:00:00+00:00") == []


# ---- card top-up approval ------------------------------------------------------------------------------

def _bf_request(ledger, **overrides):
    values = dict(
        admin_telegram_id=ALICE, admin_username="alice", requested_gb=1260,
        toman_amount=2_400_000, receipt_path="", kind="bf_topup",
        bf_paid_gb=1000, bf_gift_gb=260, bf_credit_amount=2_900_000,
    )
    values.update(overrides)
    return ledger.create_request(**values)


def test_a_bf_topup_grants_paid_and_gift_and_records_the_event(ledger, granted):
    bot = FakeBot()
    request = _bf_request(ledger)

    outcome = asyncio.run(approvals.approve_request(bot, request, 999))

    assert outcome.ok
    granted.assert_awaited_once_with(ALICE, 1260, username="alice")
    [sale] = ledger_rows(ledger, "bf_card")
    assert (sale["gb"], sale["amount"], sale["username"]) == (1260, 2_400_000, "alice")
    assert ledger_rows(ledger, "card") == []
    [row] = ledger.list_black_friday_purchases()
    assert (row.kind, row.paid_gb, row.gift_gb, row.amount, row.list_amount, row.method) == (
        "topup", 1000, 260, 2_400_000, 2_900_000, "card",
    )
    assert any(chat == ALICE and "260" in text for chat, text in bot.messages)


def test_approving_a_bf_topup_twice_grants_once(ledger, granted):
    request = _bf_request(ledger)
    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    again = asyncio.run(approvals.approve_request(FakeBot(), request, 999))

    assert not again.ok
    assert again.message == texts.ALREADY_HANDLED
    assert granted.await_count == 1
    assert len(ledger_rows(ledger, "bf_card")) == 1
    assert len(ledger.list_black_friday_purchases()) == 1


def test_a_bf_topup_is_honoured_after_the_event_ended(ledger, granted, event):
    event(False)
    request = _bf_request(ledger)
    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    granted.assert_awaited_once_with(ALICE, 1260, username="alice")


def test_a_panel_failure_puts_a_bf_topup_back_to_pending(ledger, monkeypatch):
    monkeypatch.setattr(
        panel_client_module, "topup", AsyncMock(side_effect=PanelClientError("down"))
    )
    request = _bf_request(ledger)

    outcome = asyncio.run(approvals.approve_request(FakeBot(), request, 999))

    assert not outcome.ok
    assert ledger.get_request(request).status == "pending"
    assert ledger_rows(ledger, "bf_card") == []
    assert ledger.list_black_friday_purchases() == []


def test_an_unknown_request_kind_grants_nothing(ledger, granted):
    request = _bf_request(ledger, kind="something_new")

    outcome = asyncio.run(approvals.approve_request(FakeBot(), request, 999))

    assert not outcome.ok
    assert granted.await_count == 0
    assert ledger.get_request(request).status == "pending"


def test_the_review_queue_lists_bf_requests(ledger):
    request = _bf_request(ledger)
    [pending] = ledger.list_pending_requests()
    assert pending.id == request
    assert (pending.kind, pending.bf_paid_gb, pending.bf_gift_gb) == ("bf_topup", 1000, 260)
    caption = black_friday.request_caption(pending)
    assert "بلک‌فرایدی" in caption
    assert "1000" in caption and "260" in caption


# ---- card debt settlement approval ------------------------------------------------------------------------

def _settlement_request(ledger, paid=800_000, credit=1_000_000):
    return ledger.create_request(
        admin_telegram_id=ALICE, admin_username="alice", requested_gb=0,
        toman_amount=paid, receipt_path="", kind="bf_settlement", bf_credit_amount=credit,
    )


def test_a_bf_settlement_clears_the_debt_it_was_quoted_for(ledger):
    ledger.add_debt("alice", ALICE, 1_000_000)
    request = _settlement_request(ledger)

    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    assert ledger.get_debt("alice") == 0
    assert ledger.get_wallet_balance(ALICE) == 0
    assert [r["amount"] for r in ledger_rows(ledger, "settlement")] == [800_000]
    assert [r["amount"] for r in ledger_rows(ledger, "bf_discount")] == [-200_000]
    [row] = ledger.list_black_friday_purchases()
    assert (row.kind, row.method, row.amount, row.list_amount) == ("settlement", "card", 800_000, 1_000_000)


def test_a_bf_settlement_is_idempotent(ledger):
    ledger.add_debt("alice", ALICE, 2_000_000)
    request = _settlement_request(ledger)
    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    assert not asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    assert ledger.get_debt("alice") == 1_000_000
    assert len(ledger_rows(ledger, "settlement")) == 1


def test_a_debt_that_shrank_costs_pro_rata_and_the_rest_goes_to_the_wallet(ledger):
    # Quoted 1,000,000 for 800,000; the wallet drained it to 400,000 meanwhile.
    ledger.add_debt("alice", ALICE, 400_000)
    request = _settlement_request(ledger, paid=800_000, credit=1_000_000)

    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    assert ledger.get_debt("alice") == 0
    # 400,000 of debt at 0.8 is 320,000; the other 480,000 is the customer's.
    assert ledger.get_wallet_balance(ALICE) == 480_000
    assert [r["amount"] for r in ledger_rows(ledger, "settlement")] == [320_000]
    assert [r["amount"] for r in ledger_rows(ledger, "bf_discount")] == [-80_000]
    # Conservation: every toman paid is either applied or in the wallet.
    assert 320_000 + ledger.get_wallet_balance(ALICE) == 800_000


def test_a_debt_that_vanished_returns_all_the_money(ledger):
    ledger.add_debt("alice", ALICE, 1_000)
    ledger.reduce_debt("alice", 1_000)
    request = _settlement_request(ledger)

    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    assert ledger.get_debt("alice") == 0
    assert ledger.get_wallet_balance(ALICE) == 800_000
    assert ledger_rows(ledger, "settlement") == []
    assert ledger_rows(ledger, "bf_discount") == []
    assert ledger.list_black_friday_purchases() == []


def test_a_debt_that_grew_only_loses_what_was_quoted(ledger):
    ledger.add_debt("alice", ALICE, 1_500_000)
    request = _settlement_request(ledger)

    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    assert ledger.get_debt("alice") == 500_000
    assert ledger.get_wallet_balance(ALICE) == 0


def test_a_bf_settlement_releases_a_locked_admin(ledger, monkeypatch):
    released = AsyncMock(return_value=True)
    monkeypatch.setattr(approvals.access_lock, "release_if_clear", released)
    ledger.add_debt("alice", ALICE, 1_000_000)
    request = _settlement_request(ledger)

    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    released.assert_awaited_once()


def test_a_bf_invoice_receipt_marks_it_paid_and_books_it_once(ledger, granted):
    priced(ledger, special=2900)
    invoice = ledger.create_invoice(
        telegram_id=ALICE, amount=2_900_000, description="x", due_at=None,
        admin_username="alice", traffic_gb=1000,
    )
    request = ledger.create_request(
        admin_telegram_id=ALICE, admin_username=None, requested_gb=0,
        toman_amount=2_400_000, receipt_path="", kind="invoice", invoice_id=invoice,
        bf_credit_amount=2_900_000,
    )

    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    assert ledger.get_invoice(invoice).status == "paid"
    granted.assert_awaited_once_with(ALICE, 1000, username="alice")
    assert [r["amount"] for r in ledger_rows(ledger, "invoice")] == [2_400_000]
    # Invoice revenue is booked at payment, already at the event price, so a
    # discount row on top would take the saving off profit a second time.
    assert ledger_rows(ledger, "bf_discount") == []
    [row] = ledger.list_black_friday_purchases()
    assert (row.kind, row.amount, row.list_amount) == ("invoice", 2_400_000, 2_900_000)


def _traffic_invoice_request(ledger):
    invoice = ledger.create_invoice(
        telegram_id=ALICE, amount=2_000_000, description="x", due_at=None,
        admin_username="alice", traffic_gb=1000,
    )
    request = ledger.create_request(
        admin_telegram_id=ALICE, admin_username=None, requested_gb=0,
        toman_amount=2_000_000, receipt_path="", kind="invoice", invoice_id=invoice,
    )
    return invoice, request


def test_a_failed_invoice_grant_leaves_no_sale_row(ledger, monkeypatch):
    monkeypatch.setattr(
        panel_client_module, "topup", AsyncMock(side_effect=PanelClientError("down"))
    )
    invoice, request = _traffic_invoice_request(ledger)

    assert not asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    assert ledger.get_invoice(invoice).status != "paid"
    assert ledger_rows(ledger, "invoice") == []


def test_a_re_approved_traffic_invoice_books_one_row_with_its_gb(ledger, monkeypatch):
    invoice, request = _traffic_invoice_request(ledger)
    monkeypatch.setattr(
        panel_client_module, "topup", AsyncMock(side_effect=PanelClientError("down"))
    )
    assert not asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    monkeypatch.setattr(
        panel_client_module, "topup", AsyncMock(return_value={"new_traffic_bytes": GB})
    )

    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok

    [row] = ledger_rows(ledger, "invoice")
    assert (row["gb"], row["amount"], row["username"]) == (1000, 2_000_000, "alice")


def test_a_manual_invoice_is_booked_without_gb_or_panel(ledger, granted):
    invoice = ledger.create_invoice(telegram_id=ALICE, amount=50_000, description="x", due_at=None)
    request = ledger.create_request(
        admin_telegram_id=ALICE, admin_username=None, requested_gb=0,
        toman_amount=50_000, receipt_path="", kind="invoice", invoice_id=invoice,
    )
    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    [row] = ledger_rows(ledger, "invoice")
    assert (row["gb"], row["username"]) == (0, None)


def test_a_normal_invoice_receipt_writes_no_discount(ledger, granted):
    invoice = ledger.create_invoice(telegram_id=ALICE, amount=50_000, description="x", due_at=None)
    request = ledger.create_request(
        admin_telegram_id=ALICE, admin_username=None, requested_gb=0,
        toman_amount=50_000, receipt_path="", kind="invoice", invoice_id=invoice,
    )
    assert asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok
    assert ledger_rows(ledger, "bf_discount") == []
    assert ledger.list_black_friday_purchases() == []


# ---- the menu button ---------------------------------------------------------------------------------------

def _rows(markup):
    return [[button.text for button in row] for row in markup.keyboard]


QUIET_LAYOUT = [
    [texts.BTN_TOPUP, texts.BTN_MY_PANELS],
    [texts.BTN_WALLET, texts.BTN_CHANGE_PASSWORD],
    [texts.BTN_TUTORIALS, texts.BTN_FORECAST],
    [texts.BTN_MY_INVOICES, texts.BTN_CREATE_PANEL],
    [texts.BTN_REQUEST_BOT, texts.BTN_REQUEST_REFERRAL],
    [texts.BTN_PANEL_PREVIEW],
    [texts.BTN_SUPPORT],
]


def test_the_main_menu_is_unchanged_outside_the_event(event):
    event(False)
    markup = keyboards.main_menu_kb()
    assert _rows(markup) == QUIET_LAYOUT
    assert all(button.style is None for row in markup.keyboard for button in row)


def test_the_main_menu_has_the_red_button_first_during_the_event(event):
    markup = keyboards.main_menu_kb()
    rows = _rows(markup)
    assert rows[0] == [texts.BTN_BLACK_FRIDAY]
    assert markup.keyboard[0][0].style == "danger"
    assert rows[1:] == QUIET_LAYOUT


def test_the_new_labels_are_menu_texts():
    assert texts.BTN_BLACK_FRIDAY in nav.ALL_MENU_TEXTS
    assert texts.BTN_BF_STATS in nav.ALL_MENU_TEXTS


def test_the_finance_section_offers_the_stats(event):
    labels = [label for row in _rows(keyboards.finance_section_kb()) for label in row]
    assert texts.BTN_BF_STATS in labels
    assert labels[-1] == texts.BTN_BACK


def test_the_payment_keyboard_has_only_card_and_wallet():
    markup = keyboards.bf_payment_methods_kb()
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert data == ["bf_pay:card", "bf_pay:wallet"]
    assert not any(d.startswith("pay_method") for d in data)


def test_bf_states_are_their_own_group():
    from backend.bot.states import BlackFriday, TopUp

    assert {s.state for s in BlackFriday.__states__}.isdisjoint(
        {s.state for s in TopUp.__states__}
    )


# ---- the forecast -------------------------------------------------------------------------------------------------

class FakeForecastBot:
    def __init__(self):
        self.sent = []

    async def send_message(self, chat_id, text, reply_markup=None, **kwargs):
        self.sent.append((chat_id, text, reply_markup))


def _run_forecast(monkeypatch, username="alice", telegram_id=ALICE):
    admins = [{"username": username, "telegram_id": telegram_id, "traffic": 100 * GB, "is_active": True}]
    monkeypatch.setattr(forecast.panel_client, "list_all_admins", AsyncMock(return_value=admins))
    bot = FakeForecastBot()
    assert asyncio.run(forecast.send_daily_forecasts(bot)) == 1
    return bot.sent[0]


def test_the_forecast_is_unchanged_outside_the_event(ledger, event, monkeypatch):
    event(False)
    ledger.add_debt("alice", ALICE, 1_000_000)
    chat, text, markup = _run_forecast(monkeypatch)
    body, show_buy = forecast.render("alice", 100 * GB)
    assert text == texts.FORECAST_TITLE + body
    assert markup == (keyboards.topup_panel_kb("alice") if show_buy else None)
    assert "بلک‌فرایدی" not in text


def test_the_forecast_carries_the_event_block_and_button(ledger, event, monkeypatch):
    priced(ledger, special=3000)
    chat, text, markup = _run_forecast(monkeypatch)
    assert "بلک‌فرایدی" in text
    assert "2,400" in text
    assert "!" not in text
    data = [b.callback_data for row in markup.inline_keyboard for b in row]
    assert "bf_open" in data
    # No debt: nothing about settling.
    assert texts.BF_FORECAST_DEBT.strip() not in text


def test_the_forecast_tells_a_debtor_how_much_they_save(ledger, event, monkeypatch):
    priced(ledger, special=3000)
    ledger.add_debt("alice", ALICE, 1_000_000)
    _, text, _ = _run_forecast(monkeypatch)
    assert texts.BF_FORECAST_DEBT.strip() in text
    assert "200,000" in text


def test_the_forecast_hides_the_saving_for_a_cheap_price(ledger, event, monkeypatch):
    priced(ledger, special=2200)
    ledger.add_debt("alice", ALICE, 1_000_000)
    _, text, _ = _run_forecast(monkeypatch)
    assert texts.BF_FORECAST_DEBT.strip() in text
    assert "صرفه‌جویی" not in text


# ---- stats ------------------------------------------------------------------------------------------------------------

def test_stats_with_nothing_bought(ledger, event):
    text = black_friday.stats_text()
    assert texts.BF_STATS_NONE.strip() in text


def test_stats_summarise_purchases_settlements_and_buyers(ledger, event, monkeypatch):
    import backend.utils.settings_store as store

    monkeypatch.setattr(
        store, "black_friday_state",
        lambda: {"active": True, "ends_at": "2026-11-29T23:59:59+03:30"},
    )
    add = ledger.insert_black_friday_purchase
    add(telegram_id=ALICE, username="alice", kind="topup", paid_gb=1000, gift_gb=260,
        amount=2_400_000, list_amount=2_900_000, method="card")
    add(telegram_id=ALICE, username="alice", kind="topup", paid_gb=2000, gift_gb=360,
        amount=4_800_000, list_amount=5_800_000, method="wallet")
    add(telegram_id=BOB, username="bob", kind="topup", paid_gb=300, gift_gb=0,
        amount=720_000, list_amount=720_000, method="wallet")
    add(telegram_id=BOB, username="bob", kind="settlement", paid_gb=0, gift_gb=0,
        amount=800_000, list_amount=1_000_000, method="card")

    text = black_friday.stats_text()

    assert "3 از 2 خریدار" in text  # 3 purchases, 2 buyers
    assert "3300" in text  # GB paid
    assert "620" in text  # GB gifted
    assert "7,920,000" in text  # purchase money
    assert "1,500,000" in text  # purchase discount
    assert "200,000" in text  # settlement discount
    assert "3,200,000" in text  # card: 2,400,000 + 800,000
    assert "5,520,000" in text  # wallet: 4,800,000 + 720,000
    assert "1405/09/08" in text and "23:59" in text  # the end, in Tehran time
    assert text.index("alice") < text.index("bob")


def test_stats_name_at_most_five_top_buyers(ledger, event):
    for index in range(7):
        ledger.insert_black_friday_purchase(
            telegram_id=1000 + index, username=f"u{index}", kind="topup", paid_gb=200,
            gift_gb=0, amount=100 * (index + 1), list_amount=100 * (index + 1), method="card",
        )
    text = black_friday.stats_text()
    assert "u6" in text and "u2" in text
    assert "u1 " not in text and "u0" not in text


# ---- the handlers (money paths) -----------------------------------------------------------------------------------------

class FakeState:
    def __init__(self, data=None):
        self.data = dict(data or {})
        self.state = None

    async def get_data(self):
        return dict(self.data)

    async def update_data(self, **kwargs):
        self.data.update(kwargs)

    async def set_state(self, state):
        self.state = state

    async def clear(self):
        self.data = {}
        self.state = None


class FakeMessage:
    def __init__(self, user_id, photo=None, text=None):
        self.answers: list[str] = []
        self.from_user = SimpleNamespace(id=user_id)
        self.photo = photo
        self.text = text

    async def answer(self, text, **kwargs):
        self.answers.append(text)


class FakeCall:
    def __init__(self, user_id, data="bf_pay:wallet"):
        self.from_user = SimpleNamespace(id=user_id)
        self.message = FakeMessage(user_id)
        self.data = data
        self.alerts: list[str] = []

    async def answer(self, text=None, show_alert=False, **kwargs):
        if text:
            self.alerts.append(text)


@pytest.fixture()
def handlers(ledger, admin, granted, event, monkeypatch):
    admin()
    monkeypatch.setattr(bf_router, "settings", SimpleNamespace(superadmin_id_list=[1], media_dir="."))
    bf_router._in_flight_payments.discard(ALICE)
    yield SimpleNamespace(ledger=ledger, granted=granted)
    bf_router._in_flight_payments.discard(ALICE)


def _topup_state(ledger, username="alice", paid=1000):
    quote = black_friday.package_quote(username, paid)
    return FakeState(
        {"panel_username": username, "bf": {"kind": "topup", "panel_username": username,
                                              "quote": __import__("dataclasses").asdict(quote)}}
    )


def _pay_wallet(call, state):
    return asyncio.run(bf_router.pay_from_wallet(call, state, FakeBot()))


def test_the_wallet_pays_for_paid_plus_gift(handlers):
    priced(handlers.ledger, global_price=2900)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    state = _topup_state(handlers.ledger)
    call = FakeCall(ALICE)

    _pay_wallet(call, state)

    handlers.granted.assert_awaited_once_with(ALICE, 1260, username="alice")
    assert handlers.ledger.get_wallet_balance(ALICE) == 600_000
    [sale] = ledger_rows(handlers.ledger, "bf_wallet")
    assert (sale["gb"], sale["amount"]) == (1260, 2_400_000)
    [row] = handlers.ledger.list_black_friday_purchases()
    assert (row.paid_gb, row.gift_gb, row.amount, row.list_amount, row.method) == (
        1000, 260, 2_400_000, 2_900_000, "wallet",
    )
    assert state.state is None


def test_the_wallet_refuses_a_purchase_it_cannot_cover(handlers):
    priced(handlers.ledger, global_price=2900)
    handlers.ledger.add_wallet_balance(ALICE, 2_399_999)
    state = _topup_state(handlers.ledger)
    call = FakeCall(ALICE)

    _pay_wallet(call, state)

    assert handlers.ledger.get_wallet_balance(ALICE) == 2_399_999
    assert handlers.granted.await_count == 0
    assert state.data  # still there: they can top the wallet up and retry


def test_a_panel_failure_refunds_the_wallet(handlers, monkeypatch):
    priced(handlers.ledger, global_price=2900)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    monkeypatch.setattr(
        panel_client_module, "topup", AsyncMock(side_effect=PanelClientError("down"))
    )
    state = _topup_state(handlers.ledger)

    _pay_wallet(FakeCall(ALICE), state)

    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert ledger_rows(handlers.ledger, "bf_wallet") == []
    assert handlers.ledger.list_black_friday_purchases() == []


def test_a_debt_that_appeared_after_the_menu_blocks_the_wallet(handlers):
    priced(handlers.ledger, global_price=2900)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    state = _topup_state(handlers.ledger)
    handlers.ledger.add_debt("alice", ALICE, 10_000)

    _pay_wallet(FakeCall(ALICE), state)

    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert handlers.granted.await_count == 0


def test_nothing_is_charged_once_the_event_has_ended(handlers, event):
    priced(handlers.ledger, global_price=2900)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    state = _topup_state(handlers.ledger)
    event(False)

    _pay_wallet(FakeCall(ALICE), state)

    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert handlers.granted.await_count == 0


def test_a_price_change_re_shows_the_invoice_instead_of_charging(handlers):
    priced(handlers.ledger, global_price=2900)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    state = _topup_state(handlers.ledger)
    # The special price drops below the rate: the quoted gift and total are stale.
    handlers.ledger.set_admin_price("alice", 2000)

    _pay_wallet(FakeCall(ALICE), state)

    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert handlers.granted.await_count == 0
    assert state.data["bf"]["quote"]["total"] == 2_000_000


def test_a_double_tap_is_turned_away(handlers):
    priced(handlers.ledger, global_price=2900)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    state = _topup_state(handlers.ledger)
    bf_router._in_flight_payments.add(ALICE)
    call = FakeCall(ALICE)

    _pay_wallet(call, state)

    assert call.alerts == [texts.PAYMENT_PROCESSING]
    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert handlers.granted.await_count == 0


def _debt_state(original, discounted, username="alice"):
    return FakeState({"bf": {"kind": "debt", "username": username,
                               "original": original, "discounted": discounted}})


def test_the_wallet_settles_a_debt_at_the_event_rate(handlers):
    priced(handlers.ledger, special=3000)
    handlers.ledger.add_debt("alice", ALICE, 1_000_000)
    handlers.ledger.add_wallet_balance(ALICE, 1_000_000)
    state = _debt_state(1_000_000, 800_000)

    _pay_wallet(FakeCall(ALICE), state)

    assert handlers.ledger.get_debt("alice") == 0
    assert handlers.ledger.get_wallet_balance(ALICE) == 200_000
    assert [r["amount"] for r in ledger_rows(handlers.ledger, "settlement")] == [800_000]
    assert [r["amount"] for r in ledger_rows(handlers.ledger, "bf_discount")] == [-200_000]
    [row] = handlers.ledger.list_black_friday_purchases()
    assert (row.kind, row.method) == ("settlement", "wallet")


def test_no_partial_payment_when_the_wallet_is_short_of_the_discounted_debt(handlers):
    priced(handlers.ledger, special=3000)
    handlers.ledger.add_debt("alice", ALICE, 1_000_000)
    handlers.ledger.add_wallet_balance(ALICE, 799_999)

    _pay_wallet(FakeCall(ALICE), _debt_state(1_000_000, 800_000))

    assert handlers.ledger.get_debt("alice") == 1_000_000
    assert handlers.ledger.get_wallet_balance(ALICE) == 799_999


def test_a_debt_that_changed_is_re_quoted_not_charged(handlers):
    priced(handlers.ledger, special=3000)
    handlers.ledger.add_debt("alice", ALICE, 500_000)  # smaller than the screen said
    handlers.ledger.add_wallet_balance(ALICE, 1_000_000)
    state = _debt_state(1_000_000, 800_000)

    _pay_wallet(FakeCall(ALICE), state)

    assert handlers.ledger.get_wallet_balance(ALICE) == 1_000_000
    assert handlers.ledger.get_debt("alice") == 500_000
    assert state.data["bf"]["discounted"] == 400_000


def test_someone_elses_debt_cannot_be_paid(handlers):
    priced(handlers.ledger, special=3000)
    handlers.ledger.add_debt("alice", BOB, 1_000_000)  # belongs to BOB
    handlers.ledger.add_wallet_balance(ALICE, 1_000_000)

    _pay_wallet(FakeCall(ALICE), _debt_state(1_000_000, 800_000))

    assert handlers.ledger.get_debt("alice") == 1_000_000
    assert handlers.ledger.get_wallet_balance(ALICE) == 1_000_000


def _invoice_state(invoice_id, original, discounted):
    return FakeState({"bf": {"kind": "invoice", "invoice_id": invoice_id,
                               "original": original, "discounted": discounted}})


def _traffic_invoice(ledger):
    return ledger.create_invoice(
        telegram_id=ALICE, amount=2_900_000, description="x", due_at=None,
        admin_username="alice", traffic_gb=1000,
    )


def test_the_wallet_pays_a_traffic_invoice_and_grants_its_gb(handlers):
    priced(handlers.ledger, special=2900)
    invoice = _traffic_invoice(handlers.ledger)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)

    _pay_wallet(FakeCall(ALICE), _invoice_state(invoice, 2_900_000, 2_400_000))

    assert handlers.ledger.get_invoice(invoice).status == "paid"
    handlers.granted.assert_awaited_once_with(ALICE, 1000, username="alice")
    assert handlers.ledger.get_wallet_balance(ALICE) == 600_000
    [sale] = ledger_rows(handlers.ledger, "invoice")
    assert (sale["gb"], sale["amount"], sale["username"]) == (1000, 2_400_000, "alice")
    assert ledger_rows(handlers.ledger, "bf_discount") == []
    [row] = handlers.ledger.list_black_friday_purchases()
    assert (row.kind, row.method, row.amount, row.list_amount) == ("invoice", "wallet", 2_400_000, 2_900_000)


def test_a_failed_grant_reopens_the_invoice_and_refunds(handlers, monkeypatch):
    priced(handlers.ledger, special=2900)
    invoice = _traffic_invoice(handlers.ledger)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    monkeypatch.setattr(
        panel_client_module, "topup", AsyncMock(side_effect=PanelClientError("down"))
    )

    _pay_wallet(FakeCall(ALICE), _invoice_state(invoice, 2_900_000, 2_400_000))

    assert handlers.ledger.get_invoice(invoice).status == "pending"
    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert ledger_rows(handlers.ledger, "invoice") == []


def test_an_invoice_paid_elsewhere_in_the_meantime_is_refunded(handlers, monkeypatch):
    priced(handlers.ledger, special=2900)
    invoice = _traffic_invoice(handlers.ledger)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    # The superadmin settles it between the invoice check and the flip.
    monkeypatch.setattr(handlers.ledger, "mark_invoice_paid", lambda _id: False)

    _pay_wallet(FakeCall(ALICE), _invoice_state(invoice, 2_900_000, 2_400_000))

    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert handlers.granted.await_count == 0


def _card_receipt(handlers, monkeypatch, tmp_path, state):
    sent = []

    async def fake_send(bot, **kwargs):
        sent.append(kwargs)
        return 1

    monkeypatch.setattr(bf_router.notify, "send_receipt_to_superadmins", fake_send)
    monkeypatch.setattr(
        bf_router, "settings", SimpleNamespace(superadmin_id_list=[1], media_dir=str(tmp_path))
    )

    class DownloadingBot(FakeBot):
        async def download(self, photo, destination=None):
            open(destination, "wb").write(b"x")

    message = FakeMessage(ALICE, photo=[object()])
    asyncio.run(bf_router.get_receipt(message, state, DownloadingBot()))
    return message, sent


def test_a_card_receipt_creates_a_bf_topup_request(handlers, monkeypatch, tmp_path):
    priced(handlers.ledger, global_price=2900)
    state = _topup_state(handlers.ledger)

    message, sent = _card_receipt(handlers, monkeypatch, tmp_path, state)

    [req] = handlers.ledger.list_pending_requests()
    assert req.kind == "bf_topup"
    assert (req.requested_gb, req.toman_amount) == (1260, 2_400_000)
    assert (req.bf_paid_gb, req.bf_gift_gb, req.bf_credit_amount) == (1000, 260, 2_900_000)
    assert "بلک‌فرایدی" in sent[0]["caption"]
    assert sent[0]["kind"] == "bf_topup"


def test_a_card_receipt_is_refused_once_debt_appeared(handlers, monkeypatch, tmp_path):
    priced(handlers.ledger, global_price=2900)
    state = _topup_state(handlers.ledger)
    handlers.ledger.add_debt("alice", ALICE, 10_000)

    message, sent = _card_receipt(handlers, monkeypatch, tmp_path, state)

    assert handlers.ledger.list_pending_requests() == []
    assert sent == []
    assert message.answers == [texts.BF_RECEIPT_BLOCKED]


def test_a_debt_receipt_carries_the_original_amount(handlers, monkeypatch, tmp_path):
    priced(handlers.ledger, special=3000)
    handlers.ledger.add_debt("alice", ALICE, 1_000_000)

    _card_receipt(handlers, monkeypatch, tmp_path, _debt_state(1_000_000, 800_000))

    [req] = handlers.ledger.list_pending_requests()
    assert (req.kind, req.toman_amount, req.bf_credit_amount) == ("bf_settlement", 800_000, 1_000_000)


def test_an_invoice_receipt_is_a_plain_invoice_request_at_the_discounted_amount(
    handlers, monkeypatch, tmp_path
):
    priced(handlers.ledger, special=2900)
    invoice = _traffic_invoice(handlers.ledger)

    _card_receipt(handlers, monkeypatch, tmp_path, _invoice_state(invoice, 2_900_000, 2_400_000))

    [req] = handlers.ledger.list_pending_requests()
    assert (req.kind, req.invoice_id, req.toman_amount, req.bf_credit_amount) == (
        "invoice", invoice, 2_400_000, 2_900_000,
    )


# ---- debt priced from its own sales, not from today's price ---------------------------------

def _weekly_sale(ledger, gb, amount, username="alice"):
    ledger.record_sale(telegram_id=ALICE, username=username, gb=gb, amount=amount, method="weekly")
    ledger.add_debt(username, ALICE, amount)


def test_a_debt_bought_below_the_rate_gets_no_discount_after_a_price_rise(ledger):
    # Bought 1000 GB on credit at 2,000/GB; the price is 2,900 today. Re-pricing
    # from today's price would settle it at ~1,655/GB, below the event rate.
    _weekly_sale(ledger, 1000, 2_000_000)
    priced(ledger, special=2900)
    assert black_friday.debt_quote("alice") == (2_000_000, 2_000_000, 0)
    assert not black_friday.has_debt_saving("alice")


def test_a_debt_bought_above_the_rate_is_discounted_even_after_a_price_cut(ledger):
    _weekly_sale(ledger, 1000, 2_900_000)
    priced(ledger, special=2000)
    assert black_friday.debt_quote("alice") == (2_900_000, 2_400_000, 500_000)


def test_a_partly_paid_debt_is_priced_from_its_newest_sales(ledger):
    _weekly_sale(ledger, 1000, 2_000_000)  # older, at 2,000
    _weekly_sale(ledger, 1000, 2_900_000)  # newer, at 2,900
    ledger.reduce_debt("alice", 2_000_000)  # the oldest money is paid
    priced(ledger, special=2900)
    # What is left is the 2,900 sale: 1000 GB at 2,400.
    assert black_friday.debt_quote("alice") == (2_900_000, 2_400_000, 500_000)


def test_debt_older_than_the_ledger_falls_back_to_the_current_price(ledger):
    _weekly_sale(ledger, 1000, 2_900_000)
    ledger.add_debt("alice", ALICE, 290_000)  # no sale row behind this part
    priced(ledger, special=2900)
    original, discounted, saving = black_friday.debt_quote("alice")
    assert (original, discounted) == (3_190_000, 2_400_000 + 240_000)
    assert saving == 550_000


def test_the_auto_drain_leaves_a_cheap_old_debt_at_full_price(ledger, event):
    event(True)
    _weekly_sale(ledger, 1000, 2_000_000)
    priced(ledger, special=2900)
    ledger.add_wallet_balance(ALICE, 2_000_000)
    billing.apply_wallet_to_debts(ALICE)
    assert ledger.get_debt("alice") == 0
    assert ledger.get_wallet_balance(ALICE) == 0
    assert ledger_rows(ledger, "bf_discount") == []


def test_the_auto_drain_settles_an_expensive_debt_at_the_rate(ledger, event):
    event(True)
    _weekly_sale(ledger, 1000, 2_900_000)
    priced(ledger, special=2900)
    ledger.add_wallet_balance(ALICE, 3_000_000)
    billing.apply_wallet_to_debts(ALICE)
    assert ledger.get_debt("alice") == 0
    assert ledger.get_wallet_balance(ALICE) == 600_000
    assert [r["amount"] for r in ledger_rows(ledger, "bf_discount")] == [-500_000]


def test_a_partial_auto_drain_retires_the_same_share_of_the_debt(ledger, event):
    event(True)
    _weekly_sale(ledger, 1000, 2_900_000)
    priced(ledger, special=2900)
    ledger.add_wallet_balance(ALICE, 1_200_000)  # half of the 2,400,000 event price
    billing.apply_wallet_to_debts(ALICE)
    assert ledger.get_wallet_balance(ALICE) == 0
    assert ledger.get_debt("alice") == 1_450_000  # half of 2,900,000 is retired
    # Conservation: money in + waiver == debt retired.
    retired = 2_900_000 - ledger.get_debt("alice")
    waived = -sum(r["amount"] for r in ledger_rows(ledger, "bf_discount"))
    assert 1_200_000 + waived == retired


def test_an_invoice_is_capped_at_the_rate_not_at_a_lower_current_price(ledger):
    priced(ledger, special=2000)
    invoice_id = ledger.create_invoice(
        telegram_id=ALICE, amount=2_900_000, description="x", due_at=None,
        admin_username="alice", traffic_gb=1000,
    )
    assert black_friday.invoice_quote(ledger.get_invoice(invoice_id)) == (2_900_000, 2_400_000, 500_000)


# ---- the grant's error contract: PanelClientError means nothing was credited ---------------

def test_a_failed_grant_is_a_panel_client_error(admin, monkeypatch):
    from backend.db import crud as crud_module

    admin()

    def boom(*_args, **_kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(crud_module, "grant_admin_traffic", boom)
    with pytest.raises(PanelClientError):
        asyncio.run(panel_client_module.topup(ALICE, 10, username="alice"))


def test_the_wallet_is_refunded_when_the_grant_fails_for_any_reason(handlers, monkeypatch):
    from backend.db import crud as crud_module

    priced(handlers.ledger, special=2900)
    handlers.ledger.add_wallet_balance(ALICE, 3_000_000)
    # Use the real grant path so the error comes from inside it.
    monkeypatch.setattr(panel_client_module, "topup", _real_topup)

    def boom(*_args, **_kwargs):
        raise RuntimeError("database is locked")

    monkeypatch.setattr(crud_module, "grant_admin_traffic", boom)
    _pay_wallet(FakeCall(ALICE), _topup_state(handlers.ledger))
    assert handlers.ledger.get_wallet_balance(ALICE) == 3_000_000
    assert ledger_rows(handlers.ledger, "bf_wallet") == []


def test_a_successful_grant_still_reports_the_new_total(admin):
    admin(traffic=100 * GB)
    result = asyncio.run(_real_topup(ALICE, 10, username="alice"))
    assert result["new_traffic_bytes"] == 110 * GB


# ======================================================================================
# Black Friday: buying a NEW panel, and choosing where a volume goes
# ======================================================================================

from dataclasses import asdict as _asdict

from backend.bot import profit
from backend.bot.routers import shop as shop_router
from backend.bot.states import BlackFriday as BFStates

NEWBIE = 333
SUPER = 1


class RecMessage(FakeMessage):
    """A message that also remembers the markup of what it answered."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.markups: list = []

    async def answer(self, text, reply_markup=None, **kwargs):
        self.answers.append(text)
        self.markups.append(reply_markup)

    def callback_data(self):
        markup = self.markups[-1]
        return [b.callback_data for row in markup.inline_keyboard for b in row]


class RecCall(FakeCall):
    def __init__(self, user_id, data):
        super().__init__(user_id, data)
        self.message = RecMessage(user_id)


@pytest.fixture()
def newpanel(handlers, monkeypatch):
    """The handlers fixture plus a panel API that offers one server."""
    monkeypatch.setattr(bf_router.panel_client, "list_panels", AsyncMock(return_value=["srv1"]))
    monkeypatch.setattr(bf_router.panel_client, "check_username_taken", AsyncMock(return_value=False))
    monkeypatch.setattr(shop_router, "settings", SimpleNamespace(
        superadmin_id_list=[SUPER], media_dir=".", panel_link_url="https://panel.test/",
    ))
    bf_router._in_flight_payments.discard(NEWBIE)
    yield handlers
    bf_router._in_flight_payments.discard(NEWBIE)


def _enter_as(user_id):
    message, state = RecMessage(user_id), FakeState()
    asyncio.run(bf_router._enter(message, state, user_id))
    return message, state


def _choose(user_id, state, data):
    call = RecCall(user_id, data)
    asyncio.run(bf_router.pick_package(call, state))
    return call


def _new_panel_state(selection=None, username="newbie", password="pass1234", server="srv1"):
    """The state of someone who has just typed a valid password."""
    state = FakeState({
        "bf_sel": selection or {"kind": "pkg", "paid_gb": 1000.0},
        "bf_new_server": server, "bf_new_username": username,
    })
    message = RecMessage(NEWBIE, text=password)
    asyncio.run(bf_router.get_new_password(message, state))
    return state, message


def _pay_new(state, bot=None, user_id=NEWBIE):
    bot = bot or FakeBot()
    asyncio.run(bf_router.pay_from_wallet(FakeCall(user_id), state, bot))
    return bot


# ---- entry and the target question --------------------------------------------------------------

def test_a_user_with_no_panel_gets_the_packages_not_the_not_linked_notice(newpanel):
    message, state = _enter_as(NEWBIE)

    assert texts.NOT_LINKED_RETRY not in message.answers
    assert state.state == BFStates.choosing
    assert message.callback_data() == [
        "bf_pkg:1000", "bf_pkg:2000", "bf_pkg:3000", "bf_pkg:5000", "bf_pkg:custom",
    ]


def test_the_package_screen_shows_the_public_terms(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.set_admin_price("alice", 2000)

    message, _ = _enter_as(ALICE)  # a reseller with a special price

    labels = [b.text for row in message.markups[-1].inline_keyboard for b in row]
    assert "2,400,000" in labels[0]  # the public price, not alice's 2000
    assert "260" in labels[0]


def test_a_debtor_without_a_panel_still_meets_the_debt_screen(newpanel):
    newpanel.ledger.add_debt("ghost", NEWBIE, 10_000)

    message, state = _enter_as(NEWBIE)

    assert state.state is None
    assert message.answers[0].startswith(texts.BF_BLOCKED_BY_DEBT.split("{")[0])


def test_a_package_with_no_panel_goes_straight_to_the_new_panel_path(newpanel):
    state = FakeState()
    call = _choose(NEWBIE, state, "bf_pkg:1000")

    assert state.state == BFStates.new_username
    assert state.data["bf_new_server"] == "srv1"
    assert call.message.answers == [texts.SHOP_ASK_USERNAME]


def test_several_servers_ask_which_one(newpanel, monkeypatch):
    monkeypatch.setattr(
        bf_router.panel_client, "list_panels", AsyncMock(return_value=["srv1", "srv2"])
    )
    state = FakeState()
    call = _choose(NEWBIE, state, "bf_pkg:1000")

    assert state.state == BFStates.new_server
    assert call.message.callback_data() == ["bf_srv:srv1", "bf_srv:srv2"]

    forged = RecCall(NEWBIE, "bf_srv:evil")
    asyncio.run(bf_router.pick_server(forged, state))
    assert forged.alerts == [texts.BF_NOT_AVAILABLE]
    assert state.state == BFStates.new_server

    real = RecCall(NEWBIE, "bf_srv:srv2")
    asyncio.run(bf_router.pick_server(real, state))
    assert state.state == BFStates.new_username
    assert state.data["bf_new_server"] == "srv2"


def test_no_servers_at_all_is_reported(newpanel, monkeypatch):
    monkeypatch.setattr(bf_router.panel_client, "list_panels", AsyncMock(return_value=[]))
    state = FakeState()
    call = _choose(NEWBIE, state, "bf_pkg:1000")
    assert call.message.answers == [texts.NO_MARZBAN_PANELS]
    assert state.state is None


def test_a_pending_panel_request_stops_the_new_panel_path(newpanel):
    newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=100, receipt_path="x"
    )
    state = FakeState()
    call = _choose(NEWBIE, state, "bf_pkg:1000")
    assert call.message.answers == [texts.SHOP_ALREADY_PENDING]
    assert state.state is None


def test_a_user_with_panels_is_asked_where_the_volume_goes(newpanel):
    newpanel.ledger.ensure_panel_metadata(ALICE, ["alice"])
    state = FakeState()
    call = _choose(ALICE, state, "bf_pkg:1000")

    assert state.state == BFStates.choosing_target
    assert call.message.callback_data() == ["bf_target:p:alice", "bf_target:new"]
    labels = [b.text for row in call.message.markups[-1].inline_keyboard for b in row]
    assert "پنل شماره 1" in labels[0]
    assert labels[-1] == texts.BTN_BF_NEW_PANEL


def test_a_custom_amount_is_asked_about_its_target_too(newpanel):
    state = FakeState()
    call = _choose(ALICE, state, "bf_pkg:custom")
    assert state.state == BFStates.custom_amount

    message = RecMessage(ALICE, text="۳۰۰")
    asyncio.run(bf_router.get_custom_amount(message, state))
    assert state.state == BFStates.choosing_target
    assert state.data["bf_sel"] == {"kind": "custom", "paid_gb": 300.0}


def test_a_forged_target_for_someone_elses_panel_is_refused(newpanel, admin):
    admin(username="bobpanel", telegram_id=BOB)
    state = FakeState({"bf_sel": {"kind": "pkg", "paid_gb": 1000.0}})
    state.state = BFStates.choosing_target
    call = RecCall(ALICE, "bf_target:p:bobpanel")

    asyncio.run(bf_router.pick_target(call, state))

    assert call.alerts == [texts.NOT_LINKED_RETRY]
    assert "bf" not in state.data
    assert call.message.answers == []


@pytest.mark.parametrize(
    "special, total, gift",
    [(2000, 2_000_000, 0), (2400, 2_400_000, 0), (2900, 2_400_000, 260)],
)
def test_an_existing_panel_target_uses_that_panels_price(newpanel, special, total, gift):
    priced(newpanel.ledger, special=special)
    state = FakeState({"bf_sel": {"kind": "pkg", "paid_gb": 1000.0}})
    state.state = BFStates.choosing_target
    call = RecCall(ALICE, "bf_target:p:alice")

    asyncio.run(bf_router.pick_target(call, state))

    quote = state.data["bf"]["quote"]
    assert (quote["total"], quote["gift_gb"]) == (total, gift)
    assert state.data["bf"]["kind"] == "topup" and state.data["bf"]["panel_username"] == "alice"
    assert state.state == BFStates.awaiting_payment
    assert call.message.callback_data() == ["bf_pay:card", "bf_pay:wallet"]


def test_choosing_new_panel_from_the_target_keyboard(newpanel):
    state = FakeState({"bf_sel": {"kind": "pkg", "paid_gb": 1000.0}})
    state.state = BFStates.choosing_target
    call = RecCall(ALICE, "bf_target:new")
    asyncio.run(bf_router.pick_target(call, state))
    assert state.state == BFStates.new_username


# ---- username and password -------------------------------------------------------------------------

def test_the_new_username_follows_the_shop_rules(newpanel, monkeypatch):
    state = FakeState({"bf_sel": {"kind": "pkg", "paid_gb": 1000.0}})
    state.state = BFStates.new_username

    spaced = RecMessage(NEWBIE, text="my name")
    asyncio.run(bf_router.get_new_username(spaced, state))
    assert spaced.answers == [texts.USERNAME_INVALID]

    at_sign = RecMessage(NEWBIE, text="ali@shop")
    asyncio.run(bf_router.get_new_username(at_sign, state))
    assert at_sign.answers == [texts.USERNAME_INVALID]
    assert "bf_new_username" not in state.data

    monkeypatch.setattr(bf_router.panel_client, "check_username_taken", AsyncMock(return_value=True))
    taken = RecMessage(NEWBIE, text="alice")
    asyncio.run(bf_router.get_new_username(taken, state))
    assert taken.answers == [texts.SHOP_USERNAME_TAKEN]
    assert "bf_new_username" not in state.data

    monkeypatch.setattr(bf_router.panel_client, "check_username_taken", AsyncMock(return_value=False))
    ok = RecMessage(NEWBIE, text="  NewBie ")
    asyncio.run(bf_router.get_new_username(ok, state))
    assert state.data["bf_new_username"] == "newbie"
    assert state.state == BFStates.new_password


def test_a_weak_password_is_refused(newpanel):
    state = FakeState({
        "bf_sel": {"kind": "pkg", "paid_gb": 1000.0},
        "bf_new_server": "srv1", "bf_new_username": "newbie",
    })
    message = RecMessage(NEWBIE, text="short1")
    asyncio.run(bf_router.get_new_password(message, state))
    assert message.answers == [texts.SHOP_PASSWORD_WEAK]
    assert "bf" not in state.data


# ---- the new-panel quote ----------------------------------------------------------------------------

def test_the_new_panel_quote_uses_the_global_price(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.set_admin_price("alice", 2000)  # irrelevant to a new panel

    state, message = _new_panel_state()

    quote = state.data["bf"]["quote"]
    assert (quote["paid_gb"], quote["gift_gb"], quote["total"], quote["list_total"]) == (
        1000, 260, 2_400_000, 2_900_000,
    )
    assert state.state == BFStates.awaiting_payment
    text = message.answers[-1]
    assert "srv1" in text and "newbie" in text and "2,400,000" in text
    assert "1260" in text and "260" in text and "500,000" in text
    assert message.callback_data() == ["bf_pay:card", "bf_pay:wallet"]


def test_a_low_global_price_gives_a_new_panel_no_gift(newpanel):
    priced(newpanel.ledger, global_price=2000)
    state, _ = _new_panel_state()
    quote = state.data["bf"]["quote"]
    assert (quote["total"], quote["gift_gb"]) == (2_000_000, 0)


def test_a_custom_new_panel_gets_no_gift(newpanel):
    priced(newpanel.ledger, global_price=2900)
    state, _ = _new_panel_state(selection={"kind": "custom", "paid_gb": 300.0})
    quote = state.data["bf"]["quote"]
    assert (quote["total"], quote["gift_gb"]) == (720_000, 0)


# ---- paying from the wallet ---------------------------------------------------------------------------

def test_the_wallet_pays_for_a_new_panel_and_stores_a_complete_request(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()

    bot = _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 600_000
    req = newpanel.ledger.get_pending_panel_request(NEWBIE)
    assert (req["panel_name"], req["traffic_gb"], req["receipt_path"]) == ("srv1", 1260, "")
    assert (req["desired_username"], req["desired_password"], req["referral_code_id"]) == (
        "newbie", "pass1234", None,
    )
    assert (req["bf_total"], req["bf_paid_gb"], req["bf_gift_gb"], req["bf_list_amount"],
            req["paid_method"]) == (2_400_000, 1000, 260, 2_900_000, "wallet")
    assert state.state is None
    [(chat, text)] = bot.messages
    assert chat == SUPER and "بلک‌فرایدی" in text and "newbie" in text and "srv1" in text
    # No ledger booking until the panel exists.
    assert ledger_rows(newpanel.ledger, "bf_wallet") == []
    assert newpanel.ledger.list_black_friday_purchases() == []


def test_the_superadmin_notice_carries_the_approval_buttons(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    seen = []

    class Bot(FakeBot):
        async def send_message(self, chat_id, text, **kwargs):
            seen.append(kwargs.get("reply_markup"))

    _pay_new(state, Bot())
    req = newpanel.ledger.get_pending_panel_request(NEWBIE)
    data = [b.callback_data for row in seen[0].inline_keyboard for b in row]
    assert data == [f"panel_req_approve:{req['id']}", f"panel_req_reject:{req['id']}"]


def test_the_wallet_refuses_a_new_panel_it_cannot_cover(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 2_399_999)
    state, _ = _new_panel_state()

    _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 2_399_999
    assert newpanel.ledger.get_pending_panel_request(NEWBIE) is None
    assert state.data  # they can top up and retry


def test_a_pending_request_that_appeared_later_means_no_debit(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=10, receipt_path="x"
    )

    _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000


def test_a_request_that_loses_the_race_after_the_debit_is_refunded(newpanel, monkeypatch):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    monkeypatch.setattr(bf_router, "_create_new_panel_request", AsyncMock(return_value=None))

    _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000


def test_a_request_that_cannot_be_stored_is_refunded(newpanel, monkeypatch):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    monkeypatch.setattr(
        bf_router, "_create_new_panel_request", AsyncMock(side_effect=RuntimeError("disk"))
    )

    _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000


def test_a_taken_username_at_payment_asks_for_another_without_charging(newpanel, monkeypatch):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    monkeypatch.setattr(bf_router.panel_client, "check_username_taken", AsyncMock(return_value=True))

    _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000
    assert state.state == BFStates.new_username


def test_a_price_change_re_shows_the_new_panel_quote(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    newpanel.ledger.set_setting("price_per_gb", "2000")

    _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000
    assert state.data["bf"]["quote"]["total"] == 2_000_000


def test_nothing_is_charged_for_a_new_panel_once_the_event_ended(newpanel, event):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    event(False)

    _pay_new(state)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000
    assert newpanel.ledger.get_pending_panel_request(NEWBIE) is None


def test_a_double_tap_on_a_new_panel_is_turned_away(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    bf_router._in_flight_payments.add(NEWBIE)
    call = FakeCall(NEWBIE)

    asyncio.run(bf_router.pay_from_wallet(call, state, FakeBot()))

    assert call.alerts == [texts.PAYMENT_PROCESSING]
    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000


# ---- paying by card -------------------------------------------------------------------------------------

def _new_card_receipt(handlers, monkeypatch, tmp_path, state, user_id=NEWBIE):
    sent = []

    async def fake_send(bot, **kwargs):
        sent.append(kwargs)
        return 1

    monkeypatch.setattr(bf_router.notify, "send_receipt_to_superadmins", fake_send)
    monkeypatch.setattr(
        bf_router, "settings", SimpleNamespace(superadmin_id_list=[SUPER], media_dir=str(tmp_path))
    )

    class DownloadingBot(FakeBot):
        async def download(self, photo, destination=None):
            open(destination, "wb").write(b"x")

    message = FakeMessage(user_id, photo=[object()])
    asyncio.run(bf_router.get_receipt(message, state, DownloadingBot()))
    return message, sent


def test_a_card_receipt_creates_a_complete_new_panel_request(newpanel, monkeypatch, tmp_path):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 5_000)
    state, _ = _new_panel_state()

    message, sent = _new_card_receipt(newpanel, monkeypatch, tmp_path, state)

    req = newpanel.ledger.get_pending_panel_request(NEWBIE)
    assert req["receipt_path"].startswith(str(tmp_path))
    assert (req["traffic_gb"], req["desired_username"], req["panel_name"]) == (1260, "newbie", "srv1")
    assert (req["bf_total"], req["bf_paid_gb"], req["bf_gift_gb"], req["bf_list_amount"],
            req["paid_method"]) == (2_400_000, 1000, 260, 2_900_000, "card")
    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 5_000
    [post] = sent
    assert post["kind"] == "panel"
    assert "بلک‌فرایدی" in post["caption"] and "2,400,000" in post["caption"]
    data = [b.callback_data for row in post["reply_markup"].inline_keyboard for b in row]
    assert data == [f"panel_req_approve:{req['id']}", f"panel_req_reject:{req['id']}"]
    assert texts.SHOP_REQUEST_SUBMITTED in message.answers[0]


def test_a_card_receipt_with_a_pending_request_is_not_stored_twice(newpanel, monkeypatch, tmp_path):
    state, _ = _new_panel_state()
    newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=10, receipt_path="x"
    )

    message, sent = _new_card_receipt(newpanel, monkeypatch, tmp_path, state)

    assert sent == []
    assert message.answers == [texts.SHOP_ALREADY_PENDING]


# ---- approval and rejection ----------------------------------------------------------------------------

class ReviewBot(FakeBot):
    pass


def _approve(request_id, monkeypatch, created=None):
    created = created or AsyncMock(return_value={"id": 1})
    monkeypatch.setattr(panel_client_module, "create_admin_for_shop", created)
    call = FakeCall(SUPER, f"panel_req_approve:{request_id}")
    bot = ReviewBot()
    asyncio.run(shop_router.panel_request_approve(call, bot))
    return call, bot, created


def _reject(request_id, reason="no"):
    message = FakeMessage(SUPER, text=reason)
    bot = ReviewBot()
    state = FakeState({"reject_request_id": request_id})
    asyncio.run(shop_router.panel_request_reject_finish(message, state, bot))
    return message, bot


@pytest.mark.parametrize("method, sale_method", [("card", "bf_card"), ("wallet", "bf_wallet")])
def test_approving_a_bf_new_panel_books_the_sale_and_the_purchase(
    newpanel, monkeypatch, method, sale_method
):
    request_id = newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=1260, receipt_path="",
        desired_username="newbie", desired_password="pass1234",
        bf_total=2_400_000, bf_paid_gb=1000, bf_gift_gb=260, bf_list_amount=2_900_000,
        paid_method=method,
    )

    call, bot, created = _approve(request_id, monkeypatch)

    created.assert_awaited_once()
    assert created.await_args.kwargs["traffic_gb"] == 1260
    assert newpanel.ledger.get_panel_request(request_id)["status"] == "approved"
    [sale] = ledger_rows(newpanel.ledger, sale_method)
    assert (sale["gb"], sale["amount"], sale["username"], sale["telegram_id"]) == (
        1260, 2_400_000, "newbie", NEWBIE,
    )
    assert ledger_rows(newpanel.ledger, "shop") == []
    [row] = newpanel.ledger.list_black_friday_purchases()
    assert (row.kind, row.paid_gb, row.gift_gb, row.amount, row.list_amount, row.method,
            row.username) == ("new_panel", 1000, 260, 2_400_000, 2_900_000, method, "newbie")
    assert any(chat == NEWBIE for chat, _ in bot.messages)  # the buyer got the credentials


def test_a_ledger_failure_never_blocks_the_buyers_credentials(newpanel, monkeypatch):
    request_id = newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=1260, receipt_path="",
        desired_username="newbie", desired_password="pass1234",
        bf_total=2_400_000, bf_paid_gb=1000, bf_gift_gb=260, bf_list_amount=2_900_000,
        paid_method="card",
    )
    monkeypatch.setattr(shop_router.db, "record_sale", MagicMock(side_effect=RuntimeError("locked")))

    call, bot, _ = _approve(request_id, monkeypatch)

    assert newpanel.ledger.get_panel_request(request_id)["status"] == "approved"
    assert any(chat == NEWBIE for chat, _ in bot.messages)


def test_a_failed_panel_creation_moves_no_money(newpanel, monkeypatch):
    request_id = newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=1260, receipt_path="",
        desired_username="newbie", desired_password="pass1234",
        bf_total=2_400_000, bf_paid_gb=1000, bf_gift_gb=260, bf_list_amount=2_900_000,
        paid_method="wallet",
    )

    _approve(request_id, monkeypatch, AsyncMock(side_effect=PanelClientError("down")))

    assert newpanel.ledger.get_panel_request(request_id)["status"] == "pending"
    assert ledger_rows(newpanel.ledger, "bf_wallet") == []
    assert newpanel.ledger.list_black_friday_purchases() == []
    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 0


def test_a_normal_shop_approval_now_records_a_shop_sale(newpanel, monkeypatch):
    priced(newpanel.ledger, global_price=2900)
    request_id = newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=200, receipt_path="x",
        desired_username="plain", desired_password="pass1234",
    )

    _approve(request_id, monkeypatch)

    [sale] = ledger_rows(newpanel.ledger, "shop")
    assert (sale["gb"], sale["amount"], sale["username"], sale["telegram_id"]) == (
        200, 580_000, "plain", NEWBIE,
    )
    assert newpanel.ledger.list_black_friday_purchases() == []
    assert "shop" not in newpanel.ledger.NOT_SALES
    assert "shop" in texts.SALES_METHOD_LABELS


def test_a_shop_sale_uses_the_referral_codes_price(newpanel, monkeypatch):
    priced(newpanel.ledger, global_price=2900)
    with newpanel.ledger._connect() as conn:
        conn.execute(
            "INSERT INTO referral_codes (code, owner_telegram_id, price_per_gb, bonus_percent) "
            "VALUES ('R1', 777, 2500, 0)"
        )
        code_id = conn.execute("SELECT id FROM referral_codes WHERE code = 'R1'").fetchone()["id"]
    request_id = newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=100, receipt_path="x",
        referral_code_id=code_id, desired_username="plain", desired_password="pass1234",
    )

    _approve(request_id, monkeypatch)

    [sale] = ledger_rows(newpanel.ledger, "shop")
    assert sale["amount"] == 250_000


def test_the_shop_sale_counts_as_takings_in_the_report(newpanel, monkeypatch):
    request_id = newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=200, receipt_path="x",
        desired_username="plain", desired_password="pass1234",
    )
    priced(newpanel.ledger, global_price=2900)
    _approve(request_id, monkeypatch)
    report = profit.monthly_report(1)
    assert report["months"][0]["revenue"] == 580_000


def _wallet_paid_request(newpanel):
    priced(newpanel.ledger, global_price=2900)
    newpanel.ledger.add_wallet_balance(NEWBIE, 3_000_000)
    state, _ = _new_panel_state()
    _pay_new(state)
    return newpanel.ledger.get_pending_panel_request(NEWBIE)["id"]


def test_rejecting_a_wallet_paid_request_refunds_exactly_once(newpanel):
    request_id = _wallet_paid_request(newpanel)
    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 600_000

    message, bot = _reject(request_id)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000
    assert newpanel.ledger.get_panel_request(request_id)["status"] == "rejected"
    [(chat, text)] = bot.messages
    assert chat == NEWBIE and "2,400,000" in text and "3,000,000" in text
    assert "2,400,000" in message.answers[-1]

    again, bot2 = _reject(request_id)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 3_000_000
    assert again.answers == [texts.ALREADY_HANDLED]
    assert bot2.messages == []


def test_rejecting_a_card_paid_request_refunds_nothing(newpanel, monkeypatch, tmp_path):
    priced(newpanel.ledger, global_price=2900)
    state, _ = _new_panel_state()
    _new_card_receipt(newpanel, monkeypatch, tmp_path, state)
    request_id = newpanel.ledger.get_pending_panel_request(NEWBIE)["id"]

    message, bot = _reject(request_id)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 0
    assert newpanel.ledger.get_panel_request(request_id)["status"] == "rejected"
    assert texts.BF_NEW_REJECT_REFUND.split("{")[0] not in bot.messages[0][1]


def test_rejecting_a_normal_shop_request_refunds_nothing(newpanel):
    request_id = newpanel.ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=200, receipt_path="x",
        desired_username="plain", desired_password="pass1234",
    )
    _reject(request_id)
    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 0


def test_an_approved_request_cannot_be_rejected_into_a_refund(newpanel, monkeypatch):
    request_id = _wallet_paid_request(newpanel)
    _approve(request_id, monkeypatch)

    message, _ = _reject(request_id)

    assert newpanel.ledger.get_wallet_balance(NEWBIE) == 600_000
    assert message.answers == [texts.ALREADY_HANDLED]


def test_the_pending_list_shows_the_quoted_bf_total(newpanel, monkeypatch):
    request_id = _wallet_paid_request(newpanel)
    newpanel.ledger.set_setting("price_per_gb", "9999")  # a recompute would show this
    sent = []

    class Bot(FakeBot):
        async def send_photo(self, *args, **kwargs):
            sent.append(kwargs)

    monkeypatch.setattr(
        shop_router, "settings", SimpleNamespace(superadmin_id_list=[SUPER], media_dir=".")
    )
    message = RecMessage(SUPER)
    message.from_user = SimpleNamespace(id=SUPER)
    asyncio.run(shop_router.list_pending_panel_requests(message, Bot()))

    [caption] = message.answers
    assert "بلک‌فرایدی" in caption and "2,400,000" in caption and "newbie" in caption


# ---- schema ---------------------------------------------------------------------------------------------------

def test_the_panel_request_columns_exist_and_init_is_idempotent(ledger):
    ledger.init_db()
    ledger.init_db()
    columns = {r["name"] for r in sql(ledger, "PRAGMA table_info(panel_requests)")}
    assert {"bf_total", "bf_paid_gb", "bf_gift_gb", "bf_list_amount", "paid_method"} <= columns


def test_set_panel_request_bf_stamps_an_existing_row(ledger):
    request_id = ledger.create_panel_request_if_unowned(
        telegram_id=NEWBIE, panel_name="srv1", traffic_gb=1260, receipt_path="x"
    )
    assert ledger.set_panel_request_bf(
        request_id, total=2_400_000, paid_gb=1000, gift_gb=260,
        list_amount=2_900_000, paid_method="card",
    )
    req = ledger.get_panel_request(request_id)
    assert (req["bf_total"], req["bf_paid_gb"], req["bf_gift_gb"], req["bf_list_amount"],
            req["paid_method"]) == (2_400_000, 1000, 260, 2_900_000, "card")
    assert not ledger.set_panel_request_bf(
        999, total=1, paid_gb=1, gift_gb=0, list_amount=1, paid_method="card"
    )


# ---- menus -------------------------------------------------------------------------------------------------------

PROSPECT_LAYOUT = [
    [texts.BTN_REQUEST_PANEL, texts.BTN_MY_PANELS],
    [texts.BTN_REQUEST_REFERRAL, texts.BTN_PANEL_PREVIEW],
    [texts.BTN_SUPPORT],
]
UNLINKED_LAYOUT = [
    [texts.BTN_WALLET, texts.BTN_MY_INVOICES],
    [texts.BTN_MY_PANELS, texts.BTN_REQUEST_REFERRAL],
    [texts.BTN_PANEL_PREVIEW, texts.BTN_SUPPORT],
]


@pytest.mark.parametrize(
    "builder, layout",
    [(keyboards.prospect_menu_kb, PROSPECT_LAYOUT), (keyboards.unlinked_menu_kb, UNLINKED_LAYOUT)],
)
def test_the_prospect_and_unlinked_menus_are_unchanged_outside_the_event(event, builder, layout):
    event(False)
    markup = builder()
    assert _rows(markup) == layout
    assert all(button.style is None for row in markup.keyboard for button in row)


@pytest.mark.parametrize(
    "builder, layout",
    [(keyboards.prospect_menu_kb, PROSPECT_LAYOUT), (keyboards.unlinked_menu_kb, UNLINKED_LAYOUT)],
)
def test_the_prospect_and_unlinked_menus_get_the_red_button_during_the_event(event, builder, layout):
    markup = builder()
    rows = _rows(markup)
    assert rows[0] == [texts.BTN_BLACK_FRIDAY]
    assert markup.keyboard[0][0].style == "danger"
    assert rows[1:] == layout


# ---- stats -----------------------------------------------------------------------------------------------------------

def test_stats_count_new_panel_purchases_beside_topups(ledger, event, monkeypatch):
    import backend.utils.settings_store as store

    monkeypatch.setattr(store, "black_friday_state", lambda: {"active": True, "ends_at": None})
    add = ledger.insert_black_friday_purchase
    add(telegram_id=ALICE, username="alice", kind="topup", paid_gb=1000, gift_gb=260,
        amount=2_400_000, list_amount=2_900_000, method="card")
    add(telegram_id=NEWBIE, username="newbie", kind="new_panel", paid_gb=2000, gift_gb=360,
        amount=4_800_000, list_amount=5_800_000, method="wallet")

    text = black_friday.stats_text()
    assert "2 از 2 خریدار" in text
    assert "3000" in text and "620" in text
    assert "7,200,000" in text  # purchase money
    assert "1,500,000" in text  # discount
    assert "4,800,000" in text  # wallet

    summary = profit.black_friday_summary()
    assert summary["purchases"] == 2 and summary["buyers"] == 2
    assert (summary["paid_gb"], summary["gift_gb"], summary["amount"], summary["discount"]) == (
        3000, 620, 7_200_000, 1_500_000,
    )
    assert summary["cost"] == round(3620 * profit.cost_per_gb())
    assert summary["profit"] == 7_200_000 - summary["cost"]
    assert summary["settlements"] == 0
