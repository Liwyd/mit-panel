"""Shared navigation: every FSM handler that expects free text (or a photo/
video/document) must exclude these labels via `~F.text.in_(ALL_MENU_TEXTS)` on
its filter. Without that, tapping any other menu button while mid-flow gets
swallowed by the waiting handler and misread as invalid input for that state,
with no way out. Excluding these lets the tap fall through to its real
handler instead (which is state-agnostic and simply restarts cleanly), and
the dedicated Cancel handler (routers/start.py) catches BTN_CANCEL itself.
"""

from __future__ import annotations

from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from backend.bot import keyboards, texts
from backend.bot import db
from backend.bot.config import bot_config as settings

ALL_MENU_TEXTS = {
    texts.BTN_CANCEL,
    texts.BTN_TOPUP,
    texts.BTN_BALANCE,
    texts.BTN_CHANGE_PASSWORD,
    texts.BTN_CREATE_PANEL,
    texts.BTN_ADD_PANEL,
    texts.BTN_TUTORIALS,
    texts.BTN_ADD_TUTORIAL,
    texts.BTN_DELETE_TUTORIAL,
    texts.BTN_VIEW_TUTORIALS,
    texts.BTN_SEC_PANELS,
    texts.BTN_SEC_FINANCE,
    texts.BTN_SEC_USERS,
    texts.BTN_SEC_SETTINGS,
    texts.BTN_BACK,
    texts.BTN_TOGGLE_AUTO_APPROVE,
    texts.BTN_MESSAGE_USER,
    texts.BTN_PENDING_REQUESTS,
    texts.BTN_TOGGLE_FORCE_JOIN,
    texts.BTN_SET_FORCE_JOIN_CHANNEL,
    texts.BTN_SET_PRICE,
    texts.BTN_SET_CARD,
    texts.BTN_SET_ADMIN_PRICE,
    texts.BTN_LIST_ADMIN_PRICE,
    texts.BTN_CLEAR_ADMIN_PRICE,
    texts.BTN_PAY,
    texts.BTN_PAY_CARD,
    texts.BTN_SYNC_TELEGRAM_IDS,
    texts.BTN_MY_PANELS,
    texts.BTN_ALL_PANELS,
    texts.BTN_GRANT_TRAFFIC,
    texts.BTN_BROADCAST,
    texts.BTN_TOPUP_THIS_PANEL,
    texts.BTN_WALLET,
    texts.BTN_CHARGE_WALLET,
    texts.BTN_PAY_WALLET,
    texts.BTN_PAY_WEEKLY,
    texts.BTN_PAY_DEBT,
    texts.BTN_DEBTS,
    texts.BTN_TOGGLE_WEEKLY,
    texts.BTN_GRANT_WALLET,
    texts.BTN_CREATE_ADMIN,
    texts.BTN_NEW_INVOICE,
    texts.BTN_INVOICES,
    texts.BTN_PAY_INVOICE,
    texts.BTN_MY_INVOICES,
    texts.BTN_FORECAST,
    texts.BTN_SEARCH_USER,
    texts.BTN_PARTNERSHIP,
    texts.BTN_WALLET_CUSTOM,
    texts.BTN_SKIP,
    texts.BTN_MY_REFERRAL,
    texts.BTN_REQUEST_PANEL,
    texts.BTN_MANAGE_REFERRALS,
    texts.BTN_ADD_REFERRAL_CODE,
    texts.BTN_LIST_REFERRAL_CODES,
    texts.BTN_DISABLE_REFERRAL,
    texts.BTN_APPROVE_REQUEST,
    texts.BTN_REJECT_REQUEST,
    texts.BTN_DELETE_ADMIN,
    texts.BTN_SUPPORT,
    texts.BTN_PANEL_PREVIEW,
    texts.BTN_REQUEST_REFERRAL,
    texts.BTN_APPROVE_REFERRAL,
    texts.BTN_REJECT_REFERRAL,
    texts.BTN_PENDING_REFERRAL_REQUESTS,
}


# Which section each superadmin currently has open. Finishing an action returns
# them to it rather than to the root menu, so setting the price and then the card
# number doesn't mean walking back in through Settings each time. In memory on
# purpose: it is a UI position, not data, and falling back to the root menu after
# a restart is the right thing to do anyway.
_open_section: dict[int, str] = {}


def remember_section(user_id: int, section: str) -> None:
    _open_section[user_id] = section


def forget_section(user_id: int) -> None:
    _open_section.pop(user_id, None)


def superadmin_kb(user_id: int):
    """The section keyboard this superadmin is in, or the root menu."""
    builder = keyboards.SECTION_KEYBOARDS.get(_open_section.get(user_id))
    return builder() if builder else keyboards.superadmin_menu_kb()


async def menu_kb_for(user_id: int):
    """The persistent reply keyboard this user should see outside any flow.

    Reads the linkage cached at their last successful panel lookup rather than
    calling the panel again: cancelling an action must never depend on the panel
    being reachable, and a momentary outage must not strip a linked admin's menu
    down to the unlinked one.
    """
    if user_id in settings.superadmin_id_list:
        return superadmin_kb(user_id)
    if db.is_user_linked(user_id):
        return keyboards.main_menu_kb()
    # No panel: the wallet and invoices only open once we have billed them.
    if db.has_billing_account(user_id):
        return keyboards.unlinked_menu_kb()
    return keyboards.prospect_menu_kb()


async def cancel_and_show_menu(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer(texts.CANCELLED, reply_markup=await menu_kb_for(message.from_user.id))
