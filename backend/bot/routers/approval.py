"""Superadmin-facing: approve/reject top-up requests (with a reject reason),
and message any bot user directly through the bot."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from backend.bot import keyboards, texts
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import ALL_MENU_TEXTS, forget_section, superadmin_kb
from backend.bot.states import MessageUser, RejectReason
from backend.bot import db
from backend.bot.billing import apply_wallet_to_debts
from backend.bot.panel_client import PanelClientError as NexraPanelError
from backend.bot import panel_client as nexra_panel
from backend.bot.units import bytes_to_gb

router = Router(name="approval")

router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())


# ---- on-demand list of pending requests --------------------------------------

@router.message(F.text == texts.BTN_PENDING_REQUESTS)
async def list_pending(message: Message) -> None:
    # Reached from the root menu, so stop returning them into a section.
    forget_section(message.from_user.id)
    pending = db.list_pending_requests()
    if not pending:
        await message.answer(texts.NO_PENDING_REQUESTS)
        return
    for req in pending:
        caption = (
            f"🧾 درخواست شارژ حجم #{req.id}\n"
            f"▪️ پنل: {req.admin_username}\n"
            f"👤 آیدی عددی: {req.admin_telegram_id}\n"
            f"📊 حجم درخواستی: {req.requested_gb:g} گیگابایت\n"
            f"💰 مبلغ: {req.toman_amount:,} تومان"
        )
        markup = keyboards.approval_kb(req.id, req.admin_telegram_id)
        try:
            await message.answer_photo(
                photo=FSInputFile(req.receipt_path), caption=caption, reply_markup=markup
            )
        except Exception:
            await message.answer(caption + "\n(⚠️ فایل رسید در دسترس نیست)", reply_markup=markup)


# ---- approve ----------------------------------------------------------------

@router.callback_query(F.data.startswith("topup_approve:"))
async def approve(call: CallbackQuery, bot: Bot) -> None:
    request_id = int(call.data.split(":")[1])
    req = db.get_request(request_id)
    if req is None:
        await call.answer(texts.NOT_FOUND, show_alert=True)
        return
    if not db.mark_reviewed(request_id, status="approved", reviewed_by=call.from_user.id):
        await call.answer(texts.ALREADY_HANDLED, show_alert=True)
        return

    # A wallet top-up or a debt settlement moves money, not traffic.
    if req.kind == "wallet":
        db.add_wallet_balance(req.admin_telegram_id, req.toman_amount)
        # Newly arrived money clears any outstanding weekly debt immediately.
        apply_wallet_to_debts(req.admin_telegram_id)
        balance = db.get_wallet_balance(req.admin_telegram_id)
        try:
            await bot.send_message(
                req.admin_telegram_id,
                texts.WALLET_CHARGED_ADMIN.format(amount=req.toman_amount, balance=balance),
            )
        except Exception:
            pass
        await call.answer(texts.APPROVED_TOAST)
        await call.message.edit_reply_markup(reply_markup=None)
        return

    if req.kind == "invoice":
        if not db.mark_invoice_paid(req.invoice_id):
            await call.answer(texts.INVOICE_ALREADY_PAID, show_alert=True)
            await call.message.edit_reply_markup(reply_markup=None)
            return
        try:
            await bot.send_message(
                req.admin_telegram_id, texts.INVOICE_PAID_CUSTOMER.format(id=req.invoice_id)
            )
        except Exception:
            pass
        await call.answer(texts.APPROVED_TOAST)
        await call.message.edit_reply_markup(reply_markup=None)
        return

    if req.kind == "settlement":
        db.clear_debt(req.admin_username)
        try:
            await bot.send_message(
                req.admin_telegram_id,
                texts.SETTLEMENT_APPROVED_ADMIN.format(username=req.admin_username),
            )
        except Exception:
            pass
        await call.answer(texts.APPROVED_TOAST)
        await call.message.edit_reply_markup(reply_markup=None)
        return

    try:
        result = await nexra_panel.topup(
            req.admin_telegram_id, req.requested_gb, username=req.admin_username
        )
    except NexraPanelError as exc:
        db.revert_to_pending(request_id)
        await call.answer(f"{texts.PANEL_ERROR_TOAST} ({exc})", show_alert=True)
        return

    # A successful top-up rearms the low-traffic warnings for this panel.
    db.clear_warning_bucket(req.admin_username)

    new_balance_gb = bytes_to_gb(result.get("new_traffic_bytes"))
    try:
        await bot.send_message(
            req.admin_telegram_id,
            texts.REQUEST_APPROVED_ADMIN.format(
                added_gb=req.requested_gb, new_balance_gb=new_balance_gb
            ),
        )
    except Exception:
        pass

    await call.answer(texts.APPROVED_TOAST)
    await call.message.edit_reply_markup(reply_markup=None)


# ---- reject (asks for a reason first) ----------------------------------------

@router.callback_query(F.data.startswith("topup_reject:"))
async def start_reject(call: CallbackQuery, state: FSMContext) -> None:
    request_id = int(call.data.split(":")[1])
    req = db.get_request(request_id)
    if req is None:
        await call.answer(texts.NOT_FOUND, show_alert=True)
        return
    if req.status != "pending":
        await call.answer(texts.ALREADY_HANDLED, show_alert=True)
        return

    await state.set_state(RejectReason.reason)
    await state.update_data(
        request_id=request_id,
        origin_chat_id=call.message.chat.id,
        origin_message_id=call.message.message_id,
    )
    await call.answer()
    await call.message.answer(texts.ASK_REJECT_REASON, reply_markup=keyboards.cancel_kb())


@router.message(RejectReason.reason, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_reject(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    request_id = data["request_id"]
    raw_reason = (message.text or "").strip()
    reason = None if raw_reason == "-" else raw_reason

    if not db.mark_reviewed(
        request_id, status="rejected", reviewed_by=message.from_user.id, reason=reason
    ):
        await message.answer(texts.ALREADY_HANDLED, reply_markup=superadmin_kb(message.from_user.id))
        return

    req = db.get_request(request_id)
    try:
        text = (
            texts.REQUEST_REJECTED_ADMIN_WITH_REASON.format(reason=reason)
            if reason
            else texts.REQUEST_REJECTED_ADMIN
        )
        await bot.send_message(req.admin_telegram_id, text)
    except Exception:
        pass

    await message.answer(texts.REJECTED_TOAST, reply_markup=superadmin_kb(message.from_user.id))
    try:
        await bot.edit_message_reply_markup(
            chat_id=data["origin_chat_id"],
            message_id=data["origin_message_id"],
            reply_markup=None,
        )
    except Exception:
        pass


# ---- message any bot user ----------------------------------------------------

@router.callback_query(F.data.startswith("msg_user:"))
async def start_message_user(call: CallbackQuery, state: FSMContext) -> None:
    target_id = int(call.data.split(":")[1])
    await state.set_state(MessageUser.text)
    await state.update_data(target_telegram_id=target_id)
    await call.answer()
    await call.message.answer(texts.ASK_MESSAGE_TEXT, reply_markup=keyboards.cancel_kb())


@router.message(MessageUser.text, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_message_user(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    await state.clear()
    target_id = data["target_telegram_id"]
    try:
        await bot.send_message(target_id, texts.INCOMING_MESSAGE_PREFIX + (message.text or ""))
        await message.answer(texts.MESSAGE_SENT, reply_markup=superadmin_kb(message.from_user.id))
    except Exception:
        await message.answer(texts.MESSAGE_FAILED, reply_markup=superadmin_kb(message.from_user.id))
