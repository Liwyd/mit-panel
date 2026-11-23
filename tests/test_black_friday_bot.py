"""Black Friday in the bot: pricing, who may buy, settling debt at the event
rate, the approval paths and the places the event touches existing behaviour.

`backend.bot.db` is pointed at a temp SQLite file by the `ledger` fixture, and
the panel's own database is an in-memory one (see conftest), so nothing here
reaches live data. The event switch is patched on `black_friday.is_active`, the
single function every other module asks.
"""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock

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


def test_a_bf_invoice_receipt_marks_it_paid_and_writes_the_discount(ledger, granted):
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
    assert [r["amount"] for r in ledger_rows(ledger, "bf_discount")] == [-500_000]
    [row] = ledger.list_black_friday_purchases()
    assert (row.kind, row.amount, row.list_amount) == ("invoice", 2_400_000, 2_900_000)


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
    assert [r["amount"] for r in ledger_rows(handlers.ledger, "bf_discount")] == [-500_000]


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
