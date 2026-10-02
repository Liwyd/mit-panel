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


def test_the_card_offers_one_reminder_however_many_debts(ledger):
    _two_debts(ledger)
    ledger.add_debt("bob", 111, 10_000)

    customers = bills.by_customer(bills.open_bills(111))
    kb = keyboards.bill_actions_kb(customers[0])
    rows = [[button.text for button in row] for row in kb.inline_keyboard]

    assert [text for row in rows for text in row] == [
        texts.BTN_WARN_CUSTOMER,
        texts.BTN_MESSAGE_USER,
    ]
    assert kb.inline_keyboard[0][0].callback_data.startswith("warnall:")


def test_pay_buttons_match_the_debts_in_the_notice(ledger):
    _two_debts(ledger)

    items = sorted(bills.open_bills(111), key=bills.urgency, reverse=True)
    kb = keyboards.bill_pay_all_kb(items)
    labels = [button.text for row in kb.inline_keyboard for button in row]

    assert labels == [
        texts.BTN_PAY_BILL_WEEKLY.format(username="alice"),
        texts.BTN_PAY_BILL_INVOICE.format(id=db.list_pending_invoices(111)[0].id),
    ]
