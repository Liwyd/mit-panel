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


class TogglePaymentMode(StatesGroup):
    username = State()


class GrantWallet(StatesGroup):
    telegram_id = State()
    amount = State()


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


class CreateBot(StatesGroup):
    """Collect a BotFather token and a domain, then ask the mit-seller server
    to install the bot for whichever admin is in the state's data."""

    token = State()
    domain = State()


class CreateBotPickAdmin(StatesGroup):
    """R2: the same flow, started from an admin that already exists."""

    admin = State()
    # Asked only when the picked admin has no Telegram id on their row. The
    # bot's ADMIN is that id — the panel's own row id means nothing to the
    # mit-seller server, and a bot built with it belongs to nobody.
    telegram_id = State()


class CreatePanel(StatesGroup):
    name = State()
    url = State()
    username = State()
    password = State()


class SetPricePerGb(StatesGroup):
    value = State()


class SetAdminPrice(StatesGroup):
    admin_username = State()
    price = State()


class ClearAdminPrice(StatesGroup):
    admin_username = State()


class MarkObserver(StatesGroup):
    admin_username = State()


class UnmarkObserver(StatesGroup):
    admin_username = State()


class UnlockAdmin(StatesGroup):
    admin_username = State()


class SetCardNumber(StatesGroup):
    value = State()


class SetForceJoinChannel(StatesGroup):
    value = State()


class AddTutorial(StatesGroup):
    title = State()
    content = State()


class ShopBuy(StatesGroup):
    panel = State()
    amount_gb = State()
    referral_code = State()
    username = State()
    password = State()
    receipt = State()


class ShopApprove(StatesGroup):
    reason = State()


class ReferralManage(StatesGroup):
    owner = State()
    code = State()
    bonus = State()
    price = State()


class ReferralDisable(StatesGroup):
    code_id = State()


class DeleteAdmin(StatesGroup):
    username = State()


class PanelHistory(StatesGroup):
    username = State()
