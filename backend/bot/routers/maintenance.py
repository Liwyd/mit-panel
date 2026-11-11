"""Superadmin Telegram controls for optional monthly bot hosting bills."""

import asyncio
from html import escape

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message
from aiogram.utils.keyboard import InlineKeyboardBuilder

from backend.bot import maintenance, texts
from backend.bot.config import bot_config
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import ALL_MENU_TEXTS, remember_section, superadmin_kb
from backend.bot.states import MaintenancePrice

router = Router(name="maintenance")
PAGE_SIZE = 15


def _allowed(user_id: int) -> bool:
    return user_id in bot_config.superadmin_id_list


async def _show(message: Message, page: int = 0) -> None:
    data = await asyncio.to_thread(maintenance.list_billing)
    page = max(0, min(page, max(0, (len(data["bots"]) - 1) // PAGE_SIZE)))
    kb = InlineKeyboardBuilder()
    for item in data["bots"][page * PAGE_SIZE : (page + 1) * PAGE_SIZE]:
        status = texts.MAINT_ON if item["enabled"] else texts.MAINT_OFF
        kb.button(
            text=f"{item['bot_name'][:50]} — {status}",
            callback_data=f"maint_bot:{item['bot_id']}",
        )
    kb.button(text=texts.MAINT_SET_PRICE, callback_data="maint_price")
    if page:
        kb.button(text=texts.MAINT_PREVIOUS, callback_data=f"maint_page:{page - 1}")
    if (page + 1) * PAGE_SIZE < len(data["bots"]):
        kb.button(text=texts.MAINT_NEXT, callback_data=f"maint_page:{page + 1}")
    kb.adjust(1)
    await message.answer(
        texts.MAINT_OVERVIEW.format(price=data["eur_price"])
        + ("\n" + texts.MAINT_NO_BOTS if not data["bots"] else ""),
        reply_markup=kb.as_markup(),
    )


@router.message(F.text == texts.BTN_BOT_MAINTENANCE, SuperadminFilter())
async def open_maintenance(message: Message, state: FSMContext) -> None:
    if not _allowed(message.from_user.id):
        return
    await state.clear()
    remember_section(message.from_user.id, "finance")
    await _show(message)


@router.callback_query(F.data.startswith("maint_page:"), SuperadminFilter())
async def page(call: CallbackQuery, state: FSMContext) -> None:
    if not _allowed(call.from_user.id):
        return
    await call.answer()
    await state.clear()
    raw = call.data.split(":")[-1]
    if raw.isdigit():
        await _show(call.message, int(raw))


@router.callback_query(F.data.startswith("maint_bot:"), SuperadminFilter())
async def detail(call: CallbackQuery) -> None:
    if not _allowed(call.from_user.id):
        return
    raw = call.data.split(":")[-1]
    if not raw.isdigit():
        await call.answer()
        return
    data = await asyncio.to_thread(maintenance.list_billing)
    item = next((x for x in data["bots"] if x["bot_id"] == int(raw)), None)
    if not item:
        await call.answer(texts.MAINT_BOT_NOT_FOUND, show_alert=True)
        return
    await call.answer()
    kb = InlineKeyboardBuilder()
    if item["enabled"] or item["eligible"]:
        kb.button(
            text=texts.MAINT_DISABLE if item["enabled"] else texts.MAINT_ENABLE,
            callback_data=f"maint_set:{raw}:{0 if item['enabled'] else 1}",
        )
    kb.button(text=texts.MAINT_BACK, callback_data="maint_page:0")
    kb.adjust(1)
    invoice = item["latest_invoice"]
    next_due = (
        maintenance.parse(item["next_due_at"])
        .astimezone(maintenance.TEHRAN)
        .strftime("%Y-%m-%d %H:%M")
        if item["next_due_at"]
        else texts.MAINT_NO_DATE
    )
    await call.message.answer(
        texts.MAINT_BOT_DETAILS.format(
            bot=escape(item["bot_name"]),
            admin=escape(item["admin_username"] or "—"),
            enabled=texts.MAINT_ON if item["enabled"] else texts.MAINT_OFF,
            eligible=texts.MAINT_YES if item["eligible"] else texts.MAINT_NO,
            next_due=next_due,
            invoice=f"#{invoice['invoice_id']} — {invoice['amount']:,} — {escape(invoice['status'])}"
            if invoice
            else texts.MAINT_NO_INVOICE,
        ),
        reply_markup=kb.as_markup(),
    )


@router.callback_query(F.data.startswith("maint_set:"), SuperadminFilter())
async def toggle(call: CallbackQuery) -> None:
    if not _allowed(call.from_user.id):
        return
    parts = call.data.split(":")
    if len(parts) != 3 or not parts[1].isdigit() or parts[2] not in ("0", "1"):
        await call.answer()
        return
    try:
        await asyncio.to_thread(maintenance.set_enabled, int(parts[1]), parts[2] == "1")
    except ValueError as exc:
        await call.answer(str(exc), show_alert=True)
        return
    await call.answer(texts.MAINT_SAVED)
    # Remove the old desired-state button; replaying it is still idempotent.
    await call.message.edit_reply_markup(reply_markup=None)
    await _show(call.message)


@router.callback_query(F.data == "maint_price", SuperadminFilter())
async def ask_price(call: CallbackQuery, state: FSMContext) -> None:
    if not _allowed(call.from_user.id):
        return
    await call.answer()
    await state.set_state(MaintenancePrice.value)
    from backend.bot.keyboards import cancel_kb

    await call.message.answer(texts.MAINT_ASK_PRICE, reply_markup=cancel_kb())


@router.message(MaintenancePrice.value, ~F.text.in_(ALL_MENU_TEXTS), SuperadminFilter())
async def save_price(message: Message, state: FSMContext) -> None:
    if not _allowed(message.from_user.id):
        return
    try:
        price = await asyncio.to_thread(
            maintenance.set_price, (message.text or "").strip()
        )
    except ValueError as exc:
        await message.answer(str(exc))
        return
    await state.clear()
    await message.answer(
        texts.MAINT_PRICE_SAVED.format(price=price),
        reply_markup=superadmin_kb(message.from_user.id),
    )
