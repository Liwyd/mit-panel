from aiogram.types import InlineKeyboardMarkup, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder, ReplyKeyboardBuilder

from backend.bot import texts


def main_menu_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_TOPUP)
    kb.button(text=texts.BTN_MY_PANELS)
    kb.button(text=texts.BTN_WALLET)
    kb.button(text=texts.BTN_CHANGE_PASSWORD)
    kb.button(text=texts.BTN_TUTORIALS)
    kb.button(text=texts.BTN_FORECAST)
    kb.button(text=texts.BTN_MY_INVOICES)
    kb.button(text=texts.BTN_CREATE_PANEL)
    kb.button(text=texts.BTN_REQUEST_REFERRAL)
    kb.button(text=texts.BTN_PANEL_PREVIEW)
    kb.button(text=texts.BTN_SUPPORT)
    kb.adjust(2, 2, 2, 2, 1, 1)
    return kb.as_markup(resize_keyboard=True)


def unlinked_menu_kb() -> ReplyKeyboardMarkup:
    """Someone with no panel yet still has an account with us: they can hold a
    balance and be invoiced, so the money side of the bot is open to them. The
    panel button is where activation and the requests live."""
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_WALLET)
    kb.button(text=texts.BTN_MY_INVOICES)
    kb.button(text=texts.BTN_MY_PANELS)
    kb.button(text=texts.BTN_REQUEST_REFERRAL)
    kb.button(text=texts.BTN_PANEL_PREVIEW)
    kb.button(text=texts.BTN_SUPPORT)
    kb.adjust(2, 2, 2)
    return kb.as_markup(resize_keyboard=True)


def prospect_menu_kb() -> ReplyKeyboardMarkup:
    """Shown to users who have no panel yet — shop-style."""
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_REQUEST_PANEL)
    kb.button(text=texts.BTN_MY_PANELS)
    kb.button(text=texts.BTN_REQUEST_REFERRAL)
    kb.button(text=texts.BTN_PANEL_PREVIEW)
    kb.button(text=texts.BTN_SUPPORT)
    kb.adjust(2, 2, 1)
    return kb.as_markup(resize_keyboard=True)


def panel_request_kb() -> ReplyKeyboardMarkup:
    """Shown when user has no panels — redirect to shop."""
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_REQUEST_PANEL)
    kb.button(text=texts.BTN_BACK)
    kb.adjust(1, 1)
    return kb.as_markup(resize_keyboard=True)


def _reply_kb(*labels, layout=(2,)) -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    for label in labels:
        kb.button(text=label)
    kb.adjust(*layout)
    return kb.as_markup(resize_keyboard=True)


def superadmin_menu_kb() -> ReplyKeyboardMarkup:
    """Root menu: sections, not the whole feature list.

    Twenty-odd buttons on one keyboard filled the screen and buried the one
    thing that is actually time-critical — the pending requests — so everything
    else moves a tap away, grouped by what it is for.
    """
    return _reply_kb(
        texts.BTN_PENDING_REQUESTS,
        texts.BTN_PENDING_REFERRAL_REQUESTS,
        texts.BTN_SEC_PANELS,
        texts.BTN_SEC_FINANCE,
        texts.BTN_SEC_USERS,
        texts.BTN_TUTORIALS,
        texts.BTN_SEC_SETTINGS,
        layout=(2, 2, 2, 1),
    )


def panels_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        texts.BTN_ALL_PANELS,
        texts.BTN_CREATE_ADMIN,
        texts.BTN_ADD_PANEL,
        texts.BTN_GRANT_TRAFFIC,
        texts.BTN_SYNC_TELEGRAM_IDS,
        texts.BTN_DELETE_ADMIN,
        texts.BTN_DELETE_TUTORIAL,
        texts.BTN_BACK,
        layout=(1, 2, 1, 2, 1, 1),
    )


def finance_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        texts.BTN_INVOICES,
        texts.BTN_NEW_INVOICE,
        texts.BTN_GRANT_WALLET,
        texts.BTN_TOGGLE_DELAYED,
        texts.BTN_TOGGLE_CONSUMPTION,
        texts.BTN_BACK,
        layout=(2, 2, 2, 1),
    )


def users_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        texts.BTN_SEARCH_USER,
        texts.BTN_BROADCAST,
        texts.BTN_BACK,
        layout=(2, 1),
    )


def tutorials_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        texts.BTN_VIEW_TUTORIALS,
        texts.BTN_ADD_TUTORIAL,
        texts.BTN_DELETE_TUTORIAL,
        texts.BTN_BACK,
        layout=(1, 2, 1),
    )


def settings_section_kb() -> ReplyKeyboardMarkup:
    return _reply_kb(
        texts.BTN_TOGGLE_AUTO_APPROVE,
        texts.BTN_SET_PRICE,
        texts.BTN_SET_CARD,
        texts.BTN_SET_ADMIN_PRICE,
        texts.BTN_LIST_ADMIN_PRICE,
        texts.BTN_CLEAR_ADMIN_PRICE,
        texts.BTN_TOGGLE_FORCE_JOIN,
        texts.BTN_SET_FORCE_JOIN_CHANNEL,
        texts.BTN_ADD_REFERRAL_CODE,
        texts.BTN_MANAGE_REFERRALS,
        texts.BTN_BACK,
        layout=(1, 2, 2, 2, 2, 1),
    )


SECTION_KEYBOARDS = {
    "panels": panels_section_kb,
    "finance": finance_section_kb,
    "users": users_section_kb,
    "tutorials": tutorials_section_kb,
    "settings": settings_section_kb,
}


def cancel_kb() -> ReplyKeyboardMarkup:
    kb = ReplyKeyboardBuilder()
    kb.button(text=texts.BTN_CANCEL)
    kb.adjust(1)
    return kb.as_markup(resize_keyboard=True)


def force_join_kb(channel: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    handle = channel.lstrip("@")
    kb.button(text="📢 عضویت در کانال", url=f"https://t.me/{handle}")
    kb.button(text="✅ عضو شدم", callback_data="fj_check")
    kb.adjust(1)
    return kb.as_markup()


def invoice_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY, callback_data="topup_pay")
    return kb.as_markup()


def payment_methods_kb() -> InlineKeyboardMarkup:
    """Delayed and consumption credit are gated per panel by the superadmin, but
    both buttons are shown to everyone so those without the mode get a clear
    explanation rather than silently missing an option."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY_CARD, callback_data="pay_method:card")
    kb.button(text=texts.BTN_PAY_WALLET, callback_data="pay_method:wallet")
    kb.button(text=texts.BTN_PAY_DELAYED, callback_data="pay_method:weekly")
    kb.button(text=texts.BTN_PAY_CONSUMPTION, callback_data="pay_method:consumption")
    kb.adjust(1)
    return kb.as_markup()


def invoice_due_kb() -> InlineKeyboardMarkup:
    """Preset payment deadlines, so the superadmin picks instead of typing a date."""
    from backend.bot.invoices import DUE_OPTIONS

    kb = InlineKeyboardBuilder()
    for key, (label, _) in DUE_OPTIONS.items():
        kb.button(text=label, callback_data=f"invoice_due:{key}")
    kb.adjust(1)
    return kb.as_markup()


def pay_invoice_kb(invoice_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY_INVOICE, callback_data=f"pay_invoice:{invoice_id}")
    return kb.as_markup()


def user_actions_kb(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_DEDUCT_WALLET, callback_data=f"usr_deduct:{telegram_id}")
    kb.button(text=texts.BTN_INVOICE_FOR_USER, callback_data=f"usr_invoice:{telegram_id}")
    kb.button(text=texts.BTN_DELETE_INVOICE, callback_data=f"usr_delinv:{telegram_id}")
    kb.button(text=texts.BTN_MESSAGE_USER, callback_data=f"msg_user:{telegram_id}")
    kb.adjust(2, 2)
    return kb.as_markup()


def invoice_delete_kb(invoices) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for inv in invoices:
        kb.button(text=f"🗑 #{inv.id} — {inv.amount:,}", callback_data=f"delinv:{inv.id}")
    kb.adjust(1)
    return kb.as_markup()


def pay_debt_kb(username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_PAY_DEBT, callback_data=f"pay_debt:{username}")
    return kb.as_markup()


def bill_actions_kb(customer) -> InlineKeyboardMarkup | None:
    """A warning button per open bill, plus a direct message. Nothing to offer for
    a debt with no Telegram ID on record — there is nobody to send it to."""
    if customer.telegram_id is None:
        return None
    kb = InlineKeyboardBuilder()
    for bill in customer.bills:
        if bill.kind == "invoice":
            label = texts.BTN_WARN_INVOICE.format(id=bill.invoice_id)
        else:
            label = texts.BTN_WARN_WEEKLY.format(username=bill.username)
        kb.button(text=label, callback_data=f"warn:{bill.key}")
    kb.button(text=texts.BTN_MESSAGE_USER, callback_data=f"msg_user:{customer.telegram_id}")
    kb.adjust(1)
    return kb.as_markup()


def bill_pay_kb(bill) -> InlineKeyboardMarkup:
    if bill.kind == "invoice":
        return pay_invoice_kb(bill.invoice_id)
    return pay_debt_kb(bill.username)


def wallet_amount_kb() -> InlineKeyboardMarkup:
    """Common top-up sizes, plus an escape hatch for anything else."""
    kb = InlineKeyboardBuilder()
    for amount in texts.WALLET_PRESETS:
        kb.button(text=f"{amount:,} تومان", callback_data=f"wallet_amt:{amount}")
    kb.button(text=texts.BTN_WALLET_CUSTOM, callback_data="wallet_amt:custom")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def topup_amount_kb() -> InlineKeyboardMarkup:
    """Common purchase sizes, plus an escape hatch for anything else."""
    kb = InlineKeyboardBuilder()
    for gb in texts.TOPUP_PRESETS:
        kb.button(text=f"{gb:,} GB", callback_data=f"topup_gb:{gb}")
    kb.button(text=texts.BTN_TOPUP_CUSTOM, callback_data="topup_gb:custom")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def partner_volume_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for key, label in [
        ("u1", texts.VOL_UNDER_1TB),
        ("1", texts.VOL_1TB),
        ("2", texts.VOL_2TB),
        ("3", texts.VOL_3TB),
        ("o3", texts.VOL_OVER_3TB),
    ]:
        kb.button(text=label, callback_data=f"pvol:{key}")
    kb.adjust(1)
    return kb.as_markup()


def wallet_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CHARGE_WALLET, callback_data="wallet_charge")
    return kb.as_markup()


def approval_kb(request_id: int, admin_telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="✅ تأیید", callback_data=f"topup_approve:{request_id}")
    kb.button(text="❌ رد", callback_data=f"topup_reject:{request_id}")
    kb.button(text=texts.BTN_MESSAGE_USER, callback_data=f"msg_user:{admin_telegram_id}")
    kb.adjust(2, 1)
    return kb.as_markup()


def message_user_kb(telegram_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_MESSAGE_USER, callback_data=f"msg_user:{telegram_id}")
    kb.adjust(1)
    return kb.as_markup()


def panel_picker_kb(admins, action: str) -> InlineKeyboardMarkup:
    """One button per panel. `action` routes the choice (e.g. 'topup', 'pwd')."""
    kb = InlineKeyboardBuilder()
    for a in admins:
        kb.button(text=f"▪️ {a['username']}", callback_data=f"pick:{action}:{a['username']}")
    kb.adjust(1)
    return kb.as_markup()


def panel_name_picker_kb(panel_names) -> InlineKeyboardMarkup:
    """Choose which Marzban panel a newly provisioned reseller belongs to.

    The callback carries the panel's position, not its name: Telegram caps
    callback_data at 64 bytes and a Persian panel name would blow past that.
    """
    kb = InlineKeyboardBuilder()
    for index, name in enumerate(panel_names):
        kb.button(text=f"▪️ {name}", callback_data=f"newadmin_panel:{index}")
    kb.adjust(1)
    return kb.as_markup()


def tutorials_delete_kb(tutorials) -> InlineKeyboardMarkup:
    """Same list as browsing, but each row arms a deletion instead of opening."""
    kb = InlineKeyboardBuilder()
    for t in tutorials:
        kb.button(text=f"🗑 {t.title}", callback_data=f"tutorial_del:{t.id}")
    kb.adjust(1)
    return kb.as_markup()


def confirm_delete_tutorial_kb(tutorial_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_CONFIRM_DELETE, callback_data=f"tutorial_del_yes:{tutorial_id}")
    kb.button(text=texts.BTN_KEEP, callback_data="tutorial_del_no")
    kb.adjust(1)
    return kb.as_markup()


def topup_panel_kb(username: str) -> InlineKeyboardMarkup:
    """Attached to low-traffic warnings so the admin can jump straight to topping
    up the panel the warning is about."""
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_TOPUP_THIS_PANEL, callback_data=f"pick:topup:{username}")
    return kb.as_markup()


def tutorials_list_kb(tutorials) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for t in tutorials:
        kb.button(text=t.title, callback_data=f"tutorial:{t.id}")
    kb.adjust(1)
    return kb.as_markup()


# ---------------------------------------------------------------------------
# Shop keyboards
# ---------------------------------------------------------------------------

def shop_amount_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for gb in texts.TOPUP_PRESETS:
        kb.button(text=f"{gb:,} GB", callback_data=f"shop_gb:{gb}")
    kb.button(text=texts.BTN_TOPUP_CUSTOM, callback_data="shop_gb:custom")
    kb.adjust(2, 2, 1)
    return kb.as_markup()


def shop_panel_kb(panels: list[str]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for p in panels:
        kb.button(text=p, callback_data=f"shop_panel:{p}")
    kb.adjust(1)
    return kb.as_markup()


def panel_request_approval_kb(request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_APPROVE_REQUEST, callback_data=f"panel_req_approve:{request_id}")
    kb.button(text=texts.BTN_REJECT_REQUEST, callback_data=f"panel_req_reject:{request_id}")
    kb.adjust(2)
    return kb.as_markup()


def referral_codes_kb(codes: list[dict]) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    for c in codes:
        status = "فعال" if c["enabled"] else "غیرفعال"
        label = f"{c['code']} ({status})"
        kb.button(text=label, callback_data=f"ref_disable:{c['id']}")
    kb.adjust(1)
    return kb.as_markup()


def referral_skip_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_SKIP, callback_data="shop_skip_referral")
    kb.adjust(1)
    return kb.as_markup()


def delete_admin_confirm_kb(username: str) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.DELETE_ADMIN_YES, callback_data=f"del_admin_yes:{username}")
    kb.button(text=texts.DELETE_ADMIN_NO, callback_data="del_admin_no")
    kb.adjust(2)
    return kb.as_markup()


def referral_request_approval_kb(request_id: int) -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_APPROVE_REFERRAL, callback_data=f"ref_req_approve:{request_id}")
    kb.button(text=texts.BTN_REJECT_REFERRAL, callback_data=f"ref_req_reject:{request_id}")
    kb.adjust(2)
    return kb.as_markup()
