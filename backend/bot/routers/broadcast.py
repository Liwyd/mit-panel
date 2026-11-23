"""Superadmin broadcast: queue any messages, preview them, send to an audience."""

from __future__ import annotations

import asyncio

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from backend.bot import broadcast, keyboards, texts
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import ALL_MENU_TEXTS, superadmin_kb
from backend.bot.states import Broadcast

router = Router(name="broadcast")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())

# Albums arrive as several concurrent updates; serialise read-modify-write of
# the draft so no item is lost.
_collect_lock = asyncio.Lock()


def _queue_kb() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text=texts.BTN_BROADCAST_PREVIEW, callback_data="bc:preview")
    kb.button(text=texts.BTN_BROADCAST_CLEAR, callback_data="bc:clear")
    kb.adjust(1)
    return kb.as_markup()


@router.message(F.text == texts.BTN_BROADCAST)
async def start_broadcast(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(Broadcast.collect)
    await state.update_data(draft=[])
    await message.answer(texts.ASK_BROADCAST_COLLECT, reply_markup=keyboards.cancel_kb())


@router.message(Broadcast.collect, ~F.text.in_(ALL_MENU_TEXTS))
async def collect_message(message: Message, state: FSMContext) -> None:
    async with _collect_lock:
        data = await state.get_data()
        draft: list[dict] = list(data.get("draft", []))
        group = message.media_group_id
        first_of_group = group is None or not any(d["group"] == group for d in draft)
        if len(draft) >= broadcast.MAX_DRAFT:
            if first_of_group:
                await message.answer(texts.BROADCAST_QUEUE_FULL.format(limit=broadcast.MAX_DRAFT))
            return
        draft.append(
            {
                "id": message.message_id,
                "forwarded": bool(message.forward_origin),
                "group": group,
            }
        )
        await state.update_data(draft=draft)
    if first_of_group:
        await message.answer(
            texts.BROADCAST_QUEUED.format(count=len(draft)), reply_markup=_queue_kb()
        )


@router.callback_query(F.data == "bc:clear")
async def clear_queue(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(draft=[])
    await call.answer()
    await call.message.answer(texts.BROADCAST_CLEARED)


@router.callback_query(F.data == "bc:preview")
async def preview(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    await call.answer()
    draft = (await state.get_data()).get("draft", [])
    if not draft:
        await call.message.answer(texts.BROADCAST_QUEUE_EMPTY)
        return
    chat_id = call.from_user.id
    await call.message.answer(texts.BROADCAST_PREVIEW_HEADER)
    await broadcast.send_draft(bot, chat_id, chat_id, draft)
    kb = InlineKeyboardBuilder()
    kb.button(
        text=texts.BTN_BROADCAST_ALL.format(count=len(broadcast.audience("all"))),
        callback_data="bc:send:all",
    )
    kb.button(
        text=texts.BTN_BROADCAST_LINKED.format(count=len(broadcast.audience("linked"))),
        callback_data="bc:send:linked",
    )
    kb.button(text=texts.BTN_BROADCAST_CANCEL, callback_data="bc:cancel")
    kb.adjust(1)
    await call.message.answer(
        texts.BROADCAST_CHOOSE_AUDIENCE.format(count=len(draft)), reply_markup=kb.as_markup()
    )


@router.callback_query(F.data.in_({"bc:send:all", "bc:send:linked"}))
async def send(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    kind = call.data.rsplit(":", 1)[1]
    owner = call.from_user.id
    if not broadcast.try_acquire():
        await call.answer(texts.BROADCAST_BUSY, show_alert=True)
        return
    try:
        # Popping the draft is what makes a second tap on the button a no-op.
        async with _collect_lock:
            draft = (await state.get_data()).get("draft", [])
            await state.clear()
        await call.answer()
        if not draft:
            broadcast.release()
            await call.message.answer(texts.BROADCAST_QUEUE_EMPTY)
            return
        recipients = [r for r in broadcast.audience(kind) if r != owner]
        await call.message.answer(
            texts.BROADCAST_STARTED.format(total=len(recipients)),
            reply_markup=superadmin_kb(owner),
        )
        broadcast.start_background(broadcast.run_broadcast(bot, owner, draft, recipients))
    except BaseException:
        broadcast.release()
        raise


@router.callback_query(F.data == "bc:cancel")
async def cancel(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer()
    await call.message.answer(
        texts.BROADCAST_CANCELLED, reply_markup=superadmin_kb(call.from_user.id)
    )
