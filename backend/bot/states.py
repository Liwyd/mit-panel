"""FSM state groups for multi-step bot flows."""

from aiogram.fsm.state import State, StatesGroup


class TopUp(StatesGroup):
    amount_gb = State()
    awaiting_payment = State()
    receipt = State()


class RejectReason(StatesGroup):
    reason = State()


class MessageUser(StatesGroup):
    text = State()


class ChangePassword(StatesGroup):
    current_password = State()
    new_password = State()


class Broadcast(StatesGroup):
    text = State()


class GrantTraffic(StatesGroup):
    username = State()
    amount = State()


class WalletTopUp(StatesGroup):
    amount = State()
    receipt = State()


class DebtPayment(StatesGroup):
    receipt = State()


class ToggleWeekly(StatesGroup):
    username = State()


class GrantWallet(StatesGroup):
    telegram_id = State()
    amount = State()


class Partnership(StatesGroup):
    name = State()
    volume = State()
    method = State()


class SearchUser(StatesGroup):
    query = State()


class DeductWallet(StatesGroup):
    amount = State()


class NewInvoice(StatesGroup):
    target = State()
    amount = State()
    description = State()
    due = State()


class InvoicePayment(StatesGroup):
    receipt = State()


class CreateAdmin(StatesGroup):
    username = State()
    password = State()
    panel = State()
    traffic = State()
    expiry = State()
    telegram_id = State()


class SetPricePerGb(StatesGroup):
    value = State()


class SetCardNumber(StatesGroup):
    value = State()


class SetForceJoinChannel(StatesGroup):
    value = State()


class AddTutorial(StatesGroup):
    title = State()
    content = State()


class SetBulkPin(StatesGroup):
    value = State()


class ExportCredentials(StatesGroup):
    pin = State()
