"""The money side of the bot: wallet, invoices and weekly-credit payments.

A wallet top-up, an invoice payment and a debt settlement all go through the
same receipt → superadmin approval path as a traffic purchase; what differs is
the request's `kind`, which decides what approval actually does (approvals.py).

None of it opens to someone we have no business with yet. The wallet — and with
it the card number — appears once they own a panel or have been billed.
"""

from __future__ import annotations

import os
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from backend.bot import auto_approve, keyboards, texts
from backend.bot.bills import open_bills, render_for_customer, urgency
from backend.bot.nav import ALL_MENU_TEXTS, menu_kb_for
from backend.bot.states import DebtPayment, InvoicePayment, WalletTopUp
from backend.bot import db
from backend.bot.config import bot_config as settings

router = Router(name="wallet")


def _parse_toman(raw: str | None) -> int | None:
    cleaned = (raw or "").strip().replace(",", "").replace("٬", "")
    return int(cleaned) if cleaned.isdigit() and int(cleaned) > 0 else None


async def _save_receipt(message: Message, bot: Bot) -> str:
    os.makedirs(settings.media_dir, exist_ok=True)
    path = os.path.join(settings.media_dir, f"receipt_{uuid.uuid4().hex}.jpg")
    await bot.download(message.photo[-1], destination=path)
    return path


async def _send_to_superadmins(bot: Bot, path: str, caption: str, request_id: int, user_id: int) -> None:
    caption += auto_approve.caption_note()
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_photo(
                superadmin_id,
                photo=FSInputFile(path),
                caption=caption,
                reply_markup=keyboards.approval_kb(request_id, user_id),
            )
        except Exception:
            continue


async def _has_access(message: Message, user_id: int) -> bool:
    """A hidden button isn't a gate — an old keyboard or typed text still gets
    here — so every way in to the card number checks this itself."""
    if db.has_billing_account(user_id):
        return True
    await message.answer(texts.WALLET_NOT_AVAILABLE, reply_markup=await menu_kb_for(user_id))
    return False


# ---- wallet balance & top-up -------------------------------------------------

@router.message(F.text == texts.BTN_WALLET)
async def show_wallet(message: Message) -> None:
    if not await _has_access(message, message.from_user.id):
        return
    balance = db.get_wallet_balance(message.from_user.id)
    await message.answer(
        texts.WALLET_BALANCE.format(balance=balance), reply_markup=keyboards.wallet_kb()
    )


@router.callback_query(F.data == "wallet_charge")
async def start_wallet_charge(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    if not await _has_access(call.message, call.from_user.id):
        return
    await state.set_state(WalletTopUp.amount)
    await call.message.answer(texts.ASK_WALLET_AMOUNT, reply_markup=keyboards.wallet_amount_kb())


async def _ask_for_receipt(message: Message, state: FSMContext, amount: int, user_id: int) -> None:
    # This is where the card number is revealed, so it is gated here too, not
    # only at the menu: an amount picker left over in the chat must not get past.
    if not await _has_access(message, user_id):
        await state.clear()
        return

    card_number = db.get_setting("card_number")
    if not card_number:
        await state.clear()
        await message.answer(texts.CARD_NOT_CONFIGURED, reply_markup=await menu_kb_for(user_id))
        return

    await state.update_data(wallet_amount=amount)
    await state.set_state(WalletTopUp.receipt)
    await message.answer(
        texts.WALLET_CHARGE_INSTRUCTIONS.format(amount=amount, card_number=card_number),
        reply_markup=keyboards.cancel_kb(),
    )


@router.callback_query(F.data.startswith("wallet_amt:"), WalletTopUp.amount)
async def pick_wallet_amount(call: CallbackQuery, state: FSMContext) -> None:
    choice = call.data.split(":", 1)[1]
    await call.answer()
    if choice == "custom":
        await call.message.answer(
            texts.ASK_WALLET_CUSTOM_AMOUNT, reply_markup=keyboards.cancel_kb()
        )
        return
    await _ask_for_receipt(call.message, state, int(choice), call.from_user.id)


@router.message(WalletTopUp.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def get_wallet_amount(message: Message, state: FSMContext) -> None:
    amount = _parse_toman(message.text)
    if amount is None:
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return
    await _ask_for_receipt(message, state, amount, message.from_user.id)


@router.message(WalletTopUp.receipt, ~F.text.in_(ALL_MENU_TEXTS))
async def get_wallet_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    data = await state.get_data()
    await state.clear()
    amount = data["wallet_amount"]
    path = await _save_receipt(message, bot)

    request_id = db.create_request(
        admin_telegram_id=message.from_user.id,
        admin_username=None,
        requested_gb=0,
        toman_amount=amount,
        receipt_path=path,
        kind="wallet",
    )

    await message.answer(
        texts.WALLET_CHARGE_SUBMITTED, reply_markup=await menu_kb_for(message.from_user.id)
    )
    await _send_to_superadmins(
        bot,
        path,
        f"💼 درخواست شارژ کیف پول #{request_id}\n"
        f"👤 آیدی عددی: {message.from_user.id}\n"
        f"💰 مبلغ: {amount:,} تومان",
        request_id,
        message.from_user.id,
    )


# ---- invoices and weekly credit, as one list ----------------------------------

@router.message(F.text == texts.BTN_MY_INVOICES)
async def my_invoices(message: Message) -> None:
    # An invoice and a weekly-credit debt are the same thing to whoever owes
    # them, so they come as one list, most urgent first.
    bills = sorted(open_bills(message.from_user.id), key=urgency, reverse=True)
    if not bills:
        await message.answer(texts.NO_MY_INVOICES)
        return

    if len(bills) > 1:
        await message.answer(
            texts.MY_BILLS_SUMMARY.format(total=sum(b.amount for b in bills), count=len(bills))
        )
    for bill in bills:
        await message.answer(render_for_customer(bill), reply_markup=keyboards.bill_pay_kb(bill))


@router.callback_query(F.data.startswith("pay_invoice:"))
async def start_invoice_payment(call: CallbackQuery, state: FSMContext) -> None:
    invoice_id = int(call.data.split(":", 1)[1])
    invoice = db.get_invoice(invoice_id)
    if invoice is None:
        await call.answer(texts.INVOICE_NOT_FOUND, show_alert=True)
        return
    # An invoice belongs to one person; nobody else may pay or even see it.
    if invoice.telegram_id != call.from_user.id:
        await call.answer(texts.INVOICE_NOT_FOUND, show_alert=True)
        return
    if invoice.status != "pending":
        await call.answer(texts.INVOICE_ALREADY_PAID, show_alert=True)
        return

    card_number = db.get_setting("card_number")
    if not card_number:
        await call.answer()
        await call.message.answer(texts.CARD_NOT_CONFIGURED)
        return

    await call.answer()
    await state.set_state(InvoicePayment.receipt)
    await state.update_data(invoice_id=invoice_id, invoice_amount=invoice.amount)
    await call.message.answer(
        texts.INVOICE_PAYMENT_INSTRUCTIONS.format(
            amount=invoice.amount, card_number=card_number
        ),
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(InvoicePayment.receipt, ~F.text.in_(ALL_MENU_TEXTS))
async def get_invoice_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    data = await state.get_data()
    await state.clear()
    invoice_id, amount = data["invoice_id"], data["invoice_amount"]
    path = await _save_receipt(message, bot)

    request_id = db.create_request(
        admin_telegram_id=message.from_user.id,
        admin_username=None,
        requested_gb=0,
        toman_amount=amount,
        receipt_path=path,
        kind="invoice",
        invoice_id=invoice_id,
    )

    await message.answer(
        texts.INVOICE_RECEIPT_SUBMITTED, reply_markup=await menu_kb_for(message.from_user.id)
    )
    await _send_to_superadmins(
        bot,
        path,
        f"🧾 رسید فاکتور #{invoice_id} (درخواست #{request_id})\n"
        f"👤 آیدی عددی: {message.from_user.id}\n"
        f"💰 مبلغ: {amount:,} تومان",
        request_id,
        message.from_user.id,
    )


# ---- settling a weekly-credit debt -------------------------------------------

@router.callback_query(F.data.startswith("pay_debt:"))
async def start_debt_payment(call: CallbackQuery, state: FSMContext) -> None:
    username = call.data.split(":", 1)[1]
    debt = db.get_debt_record(username)
    # The panel named in callback data comes from the client, so it is checked
    # against who is asking — otherwise anyone could pull up another panel's
    # debt, and the card number along with it.
    if not debt or debt["amount"] <= 0 or debt["telegram_id"] != call.from_user.id:
        await call.answer(texts.NO_DEBT, show_alert=True)
        return
    amount = debt["amount"]

    card_number = db.get_setting("card_number")
    if not card_number:
        await call.answer()
        await call.message.answer(texts.CARD_NOT_CONFIGURED)
        return

    await call.answer()
    await state.set_state(DebtPayment.receipt)
    await state.update_data(debt_username=username, debt_amount=amount)
    await call.message.answer(
        texts.DEBT_PAYMENT_INSTRUCTIONS.format(amount=amount, card_number=card_number),
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(DebtPayment.receipt, ~F.text.in_(ALL_MENU_TEXTS))
async def get_debt_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    data = await state.get_data()
    await state.clear()
    username, amount = data["debt_username"], data["debt_amount"]
    path = await _save_receipt(message, bot)

    request_id = db.create_request(
        admin_telegram_id=message.from_user.id,
        admin_username=username,
        requested_gb=0,
        toman_amount=amount,
        receipt_path=path,
        kind="settlement",
    )

    await message.answer(
        texts.SETTLEMENT_SUBMITTED, reply_markup=await menu_kb_for(message.from_user.id)
    )
    await _send_to_superadmins(
        bot,
        path,
        f"🗓 رسید تسویه‌ی هفتگی #{request_id}\n"
        f"▪️ پنل: {username}\n"
        f"👤 آیدی عددی: {message.from_user.id}\n"
        f"💰 مبلغ: {amount:,} تومان",
        request_id,
        message.from_user.id,
    )
