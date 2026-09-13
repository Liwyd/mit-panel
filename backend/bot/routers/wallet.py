"""Wallet: balance, topping it up by card, and settling a weekly-credit debt.

Both a wallet top-up and a debt settlement go through the same receipt →
superadmin approval path as a traffic purchase; what differs is the request's
`kind`, which decides what approval actually does (see routers/approval.py).
"""

from __future__ import annotations

import os
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from backend.bot import keyboards, texts
from backend.bot.invoices import describe_due
from backend.bot.nav import ALL_MENU_TEXTS
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


# ---- wallet balance & top-up -------------------------------------------------

@router.message(F.text == texts.BTN_WALLET)
async def show_wallet(message: Message) -> None:
    balance = db.get_wallet_balance(message.from_user.id)
    await message.answer(
        texts.WALLET_BALANCE.format(balance=balance), reply_markup=keyboards.wallet_kb()
    )


@router.callback_query(F.data == "wallet_charge")
async def start_wallet_charge(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await state.set_state(WalletTopUp.amount)
    await call.message.answer(texts.ASK_WALLET_AMOUNT, reply_markup=keyboards.wallet_amount_kb())


async def _ask_for_receipt(message: Message, state: FSMContext, amount: int) -> None:
    card_number = db.get_setting("card_number")
    if not card_number:
        await state.clear()
        await message.answer(texts.CARD_NOT_CONFIGURED, reply_markup=keyboards.main_menu_kb())
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
    await _ask_for_receipt(call.message, state, int(choice))


@router.message(WalletTopUp.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def get_wallet_amount(message: Message, state: FSMContext) -> None:
    amount = _parse_toman(message.text)
    if amount is None:
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return
    await _ask_for_receipt(message, state, amount)


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

    await message.answer(texts.WALLET_CHARGE_SUBMITTED, reply_markup=keyboards.main_menu_kb())
    await _send_to_superadmins(
        bot,
        path,
        f"💼 درخواست شارژ کیف پول #{request_id}\n"
        f"👤 آیدی عددی: {message.from_user.id}\n"
        f"💰 مبلغ: {amount:,} تومان",
        request_id,
        message.from_user.id,
    )


# ---- manual invoices ---------------------------------------------------------

@router.message(F.text == texts.BTN_MY_INVOICES)
async def my_invoices(message: Message) -> None:
    invoices = db.list_pending_invoices(message.from_user.id)
    # Weekly credit is billed through the debts table rather than as an invoice,
    # but to the customer it's just another unpaid amount — so it belongs here too.
    debts = [d for d in db.list_outstanding_debts() if d["telegram_id"] == message.from_user.id]

    if not invoices and not debts:
        await message.answer(texts.NO_MY_INVOICES)
        return

    for debt in debts:
        await message.answer(
            texts.WEEKLY_DEBT_AS_INVOICE.format(
                username=debt["username"], amount=debt["amount"]
            ),
            reply_markup=keyboards.pay_debt_kb(debt["username"]),
        )

    for inv in invoices:
        await message.answer(
            texts.INVOICE_FOR_CUSTOMER.format(
                id=inv.id,
                amount=inv.amount,
                description=inv.description or "—",
                due=describe_due(inv.due_at),
            ),
            reply_markup=keyboards.pay_invoice_kb(inv.id),
        )


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

    await message.answer(texts.INVOICE_RECEIPT_SUBMITTED, reply_markup=keyboards.main_menu_kb())
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
    amount = db.get_debt(username)
    if amount <= 0:
        await call.answer(texts.NO_DEBT, show_alert=True)
        return

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

    await message.answer(texts.SETTLEMENT_SUBMITTED, reply_markup=keyboards.main_menu_kb())
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
