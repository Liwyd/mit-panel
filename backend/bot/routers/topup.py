"""Admin-facing top-up flow:
pick panel (skipped if they own one) -> GB amount -> auto-computed invoice
-> پرداخت -> payment method (card-to-card only, for now) -> card number
-> receipt -> submit for review.
"""

from __future__ import annotations

import os
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from backend.bot import auto_approve, keyboards, texts
from backend.bot.nav import ALL_MENU_TEXTS, menu_kb_for
from backend.bot.panels import choose_panel, owned_panel
from backend.bot.states import TopUp
from backend.bot import db
from backend.bot.config import bot_config as settings
from backend.bot.panel_client import PanelClientError
from backend.bot import panel_client
from backend.bot.units import bytes_to_gb

router = Router(name="topup")


async def _ask_amount(message: Message, state: FSMContext, username: str) -> None:
    await state.update_data(panel_username=username)
    await state.set_state(TopUp.amount_gb)
    await message.answer(
        texts.ASK_AMOUNT_GB_CHOICE, reply_markup=keyboards.topup_amount_kb()
    )


@router.message(F.text == texts.BTN_TOPUP)
async def start_topup(message: Message, state: FSMContext) -> None:
    admin = await choose_panel(message, "topup")
    if admin:
        await _ask_amount(message, state, admin["username"])


@router.callback_query(F.data.startswith("pick:topup:"))
async def picked_panel_for_topup(call: CallbackQuery, state: FSMContext) -> None:
    username = call.data.split(":", 2)[2]
    target = await owned_panel(call.from_user.id, username)
    if not target:
        await call.answer(texts.NOT_LINKED_RETRY, show_alert=True)
        return
    await call.answer()
    await _ask_amount(call.message, state, username)


@router.callback_query(F.data.startswith("topup_gb:"), TopUp.amount_gb)
async def pick_amount_gb(call: CallbackQuery, state: FSMContext) -> None:
    choice = call.data.split(":", 1)[1]
    await call.answer()
    if choice == "custom":
        await call.message.answer(
            texts.ASK_AMOUNT_GB_CUSTOM, reply_markup=keyboards.cancel_kb()
        )
        return
    await _price_and_invoice(call.message, state, float(choice))


@router.message(TopUp.amount_gb, ~F.text.in_(ALL_MENU_TEXTS))
async def get_amount_gb(message: Message, state: FSMContext) -> None:
    try:
        amount = float((message.text or "").strip().replace(",", "."))
    except ValueError:
        amount = None

    if amount is None or amount <= 0:
        await message.answer(texts.INVALID_AMOUNT_GB)
        return
    # Separate messages for the two bounds: "invalid number" tells someone who
    # typed 100 nothing about what to do next.
    if amount < settings.min_gb:
        await message.answer(texts.BELOW_MIN_GB.format(min_gb=settings.min_gb))
        return
    if amount > settings.max_gb:
        await message.answer(texts.ABOVE_MAX_GB.format(max_gb=settings.max_gb))
        return

    await _price_and_invoice(message, state, amount)


async def _price_and_invoice(message: Message, state: FSMContext, amount: float) -> None:
    data = await state.get_data()
    panel_username = data.get("panel_username", "")
    price_per_gb = db.get_effective_price(panel_username)
    if not price_per_gb:
        await state.clear()
        await message.answer(texts.PRICE_NOT_SET, reply_markup=keyboards.main_menu_kb())
        return

    total_price = round(amount * price_per_gb)
    await state.update_data(amount_gb=amount, total_price=total_price)
    await state.set_state(TopUp.awaiting_payment)
    await message.answer(
        texts.INVOICE_TEXT.format(gb=amount, price=total_price),
        reply_markup=keyboards.invoice_kb(),
    )


@router.callback_query(F.data == "topup_pay", TopUp.awaiting_payment)
async def show_payment_methods(call: CallbackQuery) -> None:
    await call.answer()
    await call.message.answer(
        texts.PAYMENT_METHODS_TEXT, reply_markup=keyboards.payment_methods_kb()
    )


@router.callback_query(F.data == "pay_method:wallet", TopUp.awaiting_payment)
async def pay_from_wallet(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    username, price, gb = data["panel_username"], data["total_price"], data["amount_gb"]
    telegram_id = call.from_user.id

    balance = db.get_wallet_balance(telegram_id)
    if balance < price:
        await call.answer()
        await call.message.answer(
            texts.WALLET_INSUFFICIENT.format(price=price, balance=balance),
            reply_markup=keyboards.wallet_kb(),
        )
        return

    # Take the money first: if crediting the panel then fails we refund, which is
    # safer than crediting traffic we might never manage to charge for.
    if not db.spend_wallet(telegram_id, price):
        await call.answer()
        await call.message.answer(
            texts.WALLET_INSUFFICIENT.format(price=price, balance=db.get_wallet_balance(telegram_id)),
            reply_markup=keyboards.wallet_kb(),
        )
        return

    try:
        result = await panel_client.topup(telegram_id, gb, username=username)
    except PanelClientError as exc:
        db.add_wallet_balance(telegram_id, price)  # refund
        await call.answer()
        await call.message.answer(
            texts.WEEKLY_TOPUP_FAILED.format(error=exc), reply_markup=keyboards.main_menu_kb()
        )
        return

    await state.clear()
    db.clear_warning_bucket(username)
    new_gb = bytes_to_gb(result.get("new_traffic_bytes"))
    balance = db.get_wallet_balance(telegram_id)

    await call.answer()
    await call.message.answer(
        texts.WALLET_PAID_SUCCESS.format(
            added_gb=gb, username=username, new_gb=new_gb, balance=balance
        ),
        reply_markup=keyboards.main_menu_kb(),
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id,
                f"💼 خرید از کیف پول\n\n▪️ پنل: {username}\n👤 آیدی عددی: {telegram_id}\n"
                f"📊 حجم: {gb:g} گیگابایت\n💰 مبلغ: {price:,} تومان",
            )
        except Exception:
            continue


@router.callback_query(F.data == "pay_method:weekly", TopUp.awaiting_payment)
async def pay_weekly_credit(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    username, price, gb = data["panel_username"], data["total_price"], data["amount_gb"]
    telegram_id = call.from_user.id

    if not db.is_weekly_enabled(username):
        await call.answer(texts.WEEKLY_NOT_ENABLED, show_alert=True)
        return

    # Credit is the whole point here: the traffic lands now and is billed at the
    # end of the week, so there's no receipt or approval step.
    try:
        result = await panel_client.topup(telegram_id, gb, username=username)
    except PanelClientError as exc:
        await call.answer()
        await call.message.answer(
            texts.WEEKLY_TOPUP_FAILED.format(error=exc), reply_markup=keyboards.main_menu_kb()
        )
        return

    await state.clear()
    db.clear_warning_bucket(username)
    debt = db.add_debt(username, telegram_id, price)
    new_gb = bytes_to_gb(result.get("new_traffic_bytes"))

    await call.answer()
    await call.message.answer(
        texts.WEEKLY_TOPUP_SUCCESS.format(
            added_gb=gb, username=username, new_gb=new_gb, price=price, debt=debt
        ),
        reply_markup=keyboards.main_menu_kb(),
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id,
                texts.WEEKLY_USED_NOTIFY_SUPERADMIN.format(
                    username=username,
                    telegram_id=telegram_id,
                    added_gb=gb,
                    price=price,
                    debt=debt,
                ),
            )
        except Exception:
            continue


@router.callback_query(F.data == "pay_method:card", TopUp.awaiting_payment)
async def show_card_payment(call: CallbackQuery, state: FSMContext) -> None:
    card_number = db.get_setting("card_number")
    if not card_number:
        await call.answer()
        await call.message.answer(texts.CARD_NOT_CONFIGURED)
        return

    data = await state.get_data()
    await call.answer()
    await state.set_state(TopUp.receipt)
    await call.message.answer(
        texts.CARD_PAYMENT_INSTRUCTIONS.format(price=data["total_price"], card_number=card_number),
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(TopUp.receipt, ~F.text.in_(ALL_MENU_TEXTS))
async def get_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    data = await state.get_data()
    await state.clear()
    username = data["panel_username"]

    target = await owned_panel(message.from_user.id, username)
    if not target:
        await message.answer(
            texts.NOT_LINKED_RETRY, reply_markup=await menu_kb_for(message.from_user.id)
        )
        return

    os.makedirs(settings.media_dir, exist_ok=True)
    receipt_path = os.path.join(settings.media_dir, f"receipt_{uuid.uuid4().hex}.jpg")
    await bot.download(message.photo[-1], destination=receipt_path)

    request_id = db.create_request(
        admin_telegram_id=message.from_user.id,
        admin_username=username,
        requested_gb=data["amount_gb"],
        toman_amount=data["total_price"],
        receipt_path=receipt_path,
    )

    await message.answer(texts.REQUEST_SUBMITTED + texts.RECEIPT_WARNING, reply_markup=keyboards.main_menu_kb())

    caption = (
        f"🧾 درخواست شارژ حجم جدید #{request_id}\n"
        f"▪️ پنل: {username}\n"
        f"👤 آیدی عددی: {message.from_user.id}\n"
        f"📊 حجم درخواستی: {data['amount_gb']:g} گیگابایت\n"
        f"💰 مبلغ: {data['total_price']:,} تومان"
    ) + auto_approve.caption_note()
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_photo(
                superadmin_id,
                photo=FSInputFile(receipt_path),
                caption=caption,
                reply_markup=keyboards.approval_kb(request_id, message.from_user.id),
            )
        except Exception:
            continue
