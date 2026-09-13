"""Superadmin-facing: approve/reject top-up requests (with a reject reason),
and message any bot user directly through the bot."""

from __future__ import annotations

import os

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from backend.bot import auto_approve, keyboards, texts
from backend.bot.approvals import approve_request
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import ALL_MENU_TEXTS, forget_section, superadmin_kb
from backend.bot.states import MessageUser, RejectReason
from backend.bot import db

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
    outcome = await approve_request(bot, int(call.data.split(":")[1]), call.from_user.id)
    await call.answer(outcome.message, show_alert=outcome.alert)
    if outcome.finished:
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

    # Typing a reason can take longer than the automatic approver's minute; the
    # rejection has to win that race.
    auto_approve.hold(request_id)
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

    rejected = db.mark_reviewed(
        request_id, status="rejected", reviewed_by=message.from_user.id, reason=reason
    )
    # Released only once the status is written, so there is no gap in which the
    # automatic approver could slip in ahead of the rejection.
    auto_approve.release(request_id)
    if not rejected:
        await message.answer(texts.ALREADY_HANDLED, reply_markup=superadmin_kb(message.from_user.id))
        return

    # Clean up receipt file after rejection
    req = db.get_request(request_id)
    if req and req.receipt_path:
        try:
            os.unlink(req.receipt_path)
        except OSError:
            pass

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
