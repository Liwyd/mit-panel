"""What the superadmin's card offers for a customer with more than one debt.

Before this, each debt got its own warning button labelled with a panel name or
an invoice number that had to be matched against the message above it, and
reminding someone about three debts meant pressing three buttons and sending
three messages."""

from backend.bot import bills, db, keyboards, texts


def _two_debts(ledger) -> None:
    ledger.add_debt("alice", 111, 30_000)
    ledger.create_invoice(telegram_id=111, amount=20_000, description="setup", due_at=None)


def test_one_message_covers_every_debt(ledger):
    _two_debts(ledger)

    items = bills.open_bills(111)
    assert len(items) == 2
    message = bills.render_warning_for(items)

    assert texts.NONPAYMENT_WARNING_MULTI.split("{items}")[0] in message
    assert "30,000" in message and "20,000" in message
    assert "50,000" in message  # the total, not two separate totals
    assert texts.WARN_ITEM_WEEKLY.format(
        username="alice", amount=30_000, timing="x"
    ).split("     ")[0] in message


def test_one_debt_reads_the_same_as_the_single_debt_notice(ledger):
    ledger.add_debt("alice", 111, 30_000)

    items = bills.open_bills(111)
    assert bills.render_warning_for(items) == bills.render_warning(items[0])


def test_the_card_offers_one_action_per_debt_however_many(ledger):
    _two_debts(ledger)
    ledger.add_debt("bob", 111, 10_000)

    customers = bills.by_customer(bills.open_bills(111))
    kb = keyboards.bill_actions_kb(customers[0])
    labels = [button.text for row in kb.inline_keyboard for button in row]

    assert labels == [
        texts.BTN_WARN_CUSTOMER,
        texts.BTN_DELETE_CUSTOMER_BILL,
        texts.BTN_MESSAGE_USER,
    ]
    assert kb.inline_keyboard[0][0].callback_data.startswith("warnall:")
    assert kb.inline_keyboard[0][1].callback_data.startswith("delpick:")


def test_writing_off_needs_a_second_tap_and_says_so_to_both_sides(ledger):
    _two_debts(ledger)
    items = sorted(bills.open_bills(111), key=bills.urgency, reverse=True)

    kb = keyboards.bills_delete_kb(items)
    assert [button.callback_data for row in kb.inline_keyboard for button in row] == [
        f"billdel:{bill.key}" for bill in items
    ]

    prompt = bills.confirm_delete_text(items[0])
    confirm = keyboards.confirm_bill_delete_kb(items[0])
    labels = [button.text for row in confirm.inline_keyboard for button in row]
    assert prompt == texts.CONFIRM_DELETE_BILL_WEEKLY.format(username="alice", amount=30_000)
    assert labels == [texts.BTN_CONFIRM_DELETE, texts.BTN_KEEP]


def test_writing_off_a_weekly_debt_zeros_it_and_notifies_the_customer(ledger):
    ledger.add_debt("alice", 111, 30_000)
    bill = next(b for b in bills.open_bills(111) if b.kind == "weekly")

    done, notice = bills.write_off(bill)

    assert done == texts.BILL_DELETED_WEEKLY.format(username="alice")
    assert notice == texts.BILL_WRITTEN_OFF_WEEKLY_CUSTOMER.format(username="alice")
    # Nothing was paid, so nothing goes in the ledger — but the debt is gone
    # and its overdue stamp with it.
    assert ledger.list_sales_since("1970-01-01T00:00:00+00:00") == []
    assert bills.open_bills(111) == []


def test_writing_off_an_invoice_that_is_already_gone_reports_failure(ledger):
    invoice_id = ledger.create_invoice(
        telegram_id=111, amount=20_000, description="setup", due_at=None
    )
    bill = next(b for b in bills.open_bills(111) if b.invoice_id == invoice_id)

    # The first tap takes it off the books.
    assert bills.write_off(bill) is not None
    # Settled between the card being drawn and the second tap: say so rather
    # than claim success twice.
    assert bills.write_off(bill) is None


def test_pay_buttons_match_the_debts_in_the_notice(ledger):
    _two_debts(ledger)

    items = sorted(bills.open_bills(111), key=bills.urgency, reverse=True)
    kb = keyboards.bill_pay_all_kb(items)
    labels = [button.text for row in kb.inline_keyboard for button in row]

    assert labels == [
        texts.BTN_PAY_BILL_WEEKLY.format(username="alice"),
        texts.BTN_PAY_BILL_INVOICE.format(id=db.list_pending_invoices(111)[0].id),
    ]
