"""Reseller applications: the entry point for someone who isn't a customer yet.

Collects name, expected monthly volume and how they sell, then hands the lead to
the superadmin. Open to anyone — this is precisely the flow for people with no
panel linked.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import keyboards, texts
from backend.bot.nav import ALL_MENU_TEXTS, menu_kb_for
from backend.bot.states import Partnership
from backend.bot.config import bot_config as settings

router = Router(name="partnership")

VOLUME_LABELS = {
    "u1": texts.VOL_UNDER_1TB,
    "1": texts.VOL_1TB,
    "2": texts.VOL_2TB,
    "3": texts.VOL_3TB,
    "o3": texts.VOL_OVER_3TB,
}


@router.message(F.text == texts.BTN_PARTNERSHIP)
async def start_partnership(message: Message, state: FSMContext) -> None:
    await state.set_state(Partnership.name)
    await message.answer(texts.ASK_PARTNER_NAME, reply_markup=keyboards.cancel_kb())


@router.message(Partnership.name, ~F.text.in_(ALL_MENU_TEXTS))
async def partner_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(texts.ASK_PARTNER_NAME)
        return
    await state.update_data(partner_name=name)
    await state.set_state(Partnership.volume)
    await message.answer(texts.ASK_PARTNER_VOLUME, reply_markup=keyboards.partner_volume_kb())


@router.callback_query(F.data.startswith("pvol:"), Partnership.volume)
async def partner_volume(call: CallbackQuery, state: FSMContext) -> None:
    key = call.data.split(":", 1)[1]
    await state.update_data(partner_volume=VOLUME_LABELS.get(key, key))
    await state.set_state(Partnership.method)
    await call.answer()
    await call.message.answer(texts.ASK_PARTNER_METHOD, reply_markup=keyboards.cancel_kb())


@router.message(Partnership.method, ~F.text.in_(ALL_MENU_TEXTS))
async def partner_method(message: Message, state: FSMContext, bot: Bot) -> None:
    method = (message.text or "").strip()
    if not method:
        await message.answer(texts.ASK_PARTNER_METHOD)
        return

    data = await state.get_data()
    await state.clear()

    await message.answer(
        texts.PARTNER_SUBMITTED, reply_markup=await menu_kb_for(message.from_user.id)
    )

    user = message.from_user
    notice = texts.PARTNER_NOTIFY_SUPERADMIN.format(
        name=data["partner_name"],
        mention=f"@{user.username}" if user.username else "—",
        telegram_id=user.id,
        volume=data["partner_volume"],
        method=method,
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id, notice, reply_markup=keyboards.message_user_kb(user.id)
            )
        except Exception:
            continue
