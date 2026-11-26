"""Superadmin: switch «ادمین ویژه» (billed for real usage) on and off.

The work is in backend.bot.metering; this is only the buttons. Every confirm
screen is built from a fresh Marzban reading, and each step re-checks state,
so a stale button can never enable twice or skip the final invoice.
"""

from __future__ import annotations

import html

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import keyboards, metering, texts
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import remember_section, superadmin_kb
from backend.bot.units import bytes_to_gb
from backend.db import crud, engin

router = Router(name="metered")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())


def _candidates() -> list:
    with engin.sessionLocal() as session:
        marzban = {p.name for p in crud.get_all_panels(session) if p.panel_type == "marzban" and p.is_active}
        return [a for a in crud.get_all_admins(session) if a.panel in marzban and a.is_active]


async def _edit(message: Message, text: str, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except Exception:
        pass


async def _tell(bot: Bot, admin_id: int, text: str) -> None:
    with engin.sessionLocal() as session:
        admin = crud.get_admin_by_id(session, admin_id)
        telegram_id = admin.telegram_id if admin else None
    if telegram_id:
        try:
            await bot.send_message(int(telegram_id), text)
        except Exception:
            pass


@router.message(F.text == texts.BTN_METERED_ADMIN)
async def start(message: Message, state: FSMContext) -> None:
    remember_section(message.from_user.id, "panels")
    await state.clear()
    admins = _candidates()
    if not admins:
        await message.answer(texts.NO_METERED_CANDIDATES, reply_markup=superadmin_kb(message.from_user.id))
        return
    metered_ids = {acct["admin_id"] for acct in metering.enabled_accounts()}
    await message.answer(
        texts.ASK_PICK_METERED_ADMIN, reply_markup=keyboards.metered_admins_kb(admins, metered_ids)
    )


@router.callback_query(F.data.startswith("met:"))
async def picked(call: CallbackQuery) -> None:
    admin_id = int(call.data.split(":", 1)[1])
    await call.answer()
    await _edit(call.message, texts.METERED_READING)
    try:
        if metering.is_metered(admin_id):
            p = await metering.preview_disable(admin_id)
            text = texts.CONFIRM_METERED_OFF.format(
                username=html.escape(p["username"]), delta_gb=bytes_to_gb(p["delta"]),
                covered_gb=bytes_to_gb(p["covered"]), outstanding_gb=bytes_to_gb(p["outstanding"]),
                billable_gb=bytes_to_gb(p["billable"]), amount=p["amount"],
                balance_gb=bytes_to_gb(p["balance_after"]),
            )
            kb = keyboards.confirm_metered_kb(admin_id, turning_on=False)
        else:
            p = await metering.preview_enable(admin_id)
            text = texts.CONFIRM_METERED_ON.format(
                username=html.escape(p["username"]), counter_gb=bytes_to_gb(p["counter_bytes"]),
                credit_gb=bytes_to_gb(p["credit_bytes"]), balance_gb=bytes_to_gb(p["balance_bytes"]),
            )
            kb = keyboards.confirm_metered_kb(admin_id, turning_on=True)
    except metering.MeteringError as exc:
        await _edit(call.message, texts.METERED_FAILED.format(error=html.escape(str(exc))))
        return
    await _edit(call.message, text, reply_markup=kb)


@router.callback_query(F.data == "met_no")
async def cancel(call: CallbackQuery) -> None:
    await call.answer()
    await _edit(call.message, texts.METERED_CANCELLED)


@router.callback_query(F.data.startswith("meton:"))
async def turn_on(call: CallbackQuery, bot: Bot) -> None:
    admin_id = int(call.data.split(":", 1)[1])
    await call.answer()
    await _edit(call.message, texts.METERED_READING)  # buttons gone: no double tap
    try:
        info = await metering.enable(admin_id, by=call.from_user.id)
    except metering.MeteringError as exc:
        await _edit(call.message, texts.METERED_FAILED.format(error=html.escape(str(exc))))
        return
    name = html.escape(info["username"])
    await _edit(call.message, texts.METERED_ON_DONE.format(
        username=name, counter_gb=bytes_to_gb(info["counter_bytes"])))
    await _tell(bot, admin_id, texts.METERED_ON_ADMIN_NOTICE.format(username=name))


@router.callback_query(F.data.startswith("metoff:"))
async def turn_off(call: CallbackQuery, bot: Bot) -> None:
    admin_id = int(call.data.split(":", 1)[1])
    await call.answer()
    await _edit(call.message, texts.METERED_READING)
    with engin.sessionLocal() as session:
        admin = crud.get_admin_by_id(session, admin_id)
        username = admin.username if admin else ""
        telegram_id = admin.telegram_id if admin else None
    try:
        result = await metering.disable(admin_id)
    except metering.MeteringError as exc:
        await _edit(call.message, texts.METERED_FAILED.format(error=html.escape(str(exc))))
        return
    invoice_line = ""
    if result.invoice_id:
        delivered = bool(telegram_id) and await metering.notify_invoice(bot, int(telegram_id), result.invoice_id)
        invoice_line = texts.METERED_OFF_INVOICE_LINE.format(
            id=result.invoice_id, amount=result.amount,
            note="" if delivered else texts.METERED_NOT_DELIVERED,
        )
    name = html.escape(username)
    await _edit(call.message, texts.METERED_OFF_DONE.format(username=name, invoice_line=invoice_line))
    await _tell(bot, admin_id, texts.METERED_OFF_ADMIN_NOTICE.format(username=name))
