"""Admin-facing: change a panel's Marzban password.

The admin must prove they know the current password first — the panel API
verifies it by authenticating to Marzban as that admin, then performs the change
with its sudo credentials. The panel's own service
account is rejected server-side, so it can never be changed from here.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import keyboards, texts
from backend.bot.nav import ALL_MENU_TEXTS
from backend.bot.panels import choose_panel, owned_panel
from backend.bot.states import ChangePassword
from backend.bot.config import bot_config as settings
from backend.bot.panel_client import PanelClientError
from backend.bot import panel_client

router = Router(name="change_password")


async def _ask_current(message: Message, state: FSMContext, username: str) -> None:
    await state.update_data(panel_username=username)
    await state.set_state(ChangePassword.current_password)
    await message.answer(texts.ASK_CURRENT_PASSWORD, reply_markup=keyboards.cancel_kb())


@router.message(F.text == texts.BTN_CHANGE_PASSWORD)
async def start_change_password(message: Message, state: FSMContext) -> None:
    admin = await choose_panel(message, "pwd")
    if admin:
        await _ask_current(message, state, admin["username"])


@router.callback_query(F.data.startswith("pick:pwd:"))
async def picked_panel_for_password(call: CallbackQuery, state: FSMContext) -> None:
    username = call.data.split(":", 2)[2]
    target = await owned_panel(call.from_user.id, username)
    if not target:
        await call.answer(texts.NOT_LINKED_RETRY, show_alert=True)
        return
    await call.answer()
    await _ask_current(call.message, state, username)


@router.message(ChangePassword.current_password, ~F.text.in_(ALL_MENU_TEXTS))
async def get_current_password(message: Message, state: FSMContext) -> None:
    current = (message.text or "").strip()
    if not current:
        await message.answer(texts.INVALID_PASSWORD)
        return
    await state.update_data(current_password=current)
    await state.set_state(ChangePassword.new_password)
    await message.answer(texts.ASK_NEW_PASSWORD, reply_markup=keyboards.cancel_kb())


@router.message(ChangePassword.new_password, ~F.text.in_(ALL_MENU_TEXTS))
async def get_new_password(message: Message, state: FSMContext, bot: Bot) -> None:
    new_password = (message.text or "").strip()
    if not new_password:
        await message.answer(texts.INVALID_PASSWORD)
        return

    data = await state.get_data()
    await state.clear()
    username = data["panel_username"]

    try:
        await panel_client.change_password(
            telegram_id=message.from_user.id,
            current_password=data["current_password"],
            new_password=new_password,
            username=username,
        )
    except PanelClientError as exc:
        # 403 from the panel means either a wrong current password or the
        # protected service account; both should stop here without changing anything.
        text = (
            texts.CURRENT_PASSWORD_WRONG
            if "Current password is incorrect" in str(exc)
            else texts.PASSWORD_CHANGE_FAILED.format(error=exc)
        )
        await message.answer(text, reply_markup=keyboards.main_menu_kb())
        return

    await message.answer(
        texts.PASSWORD_APPLIED_ADMIN.format(username=username),
        reply_markup=keyboards.main_menu_kb(),
    )

    notice = texts.PASSWORD_CHANGE_NOTIFY_SUPERADMIN.format(
        username=username, telegram_id=message.from_user.id, new_password=new_password
    )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(superadmin_id, notice)
        except Exception:
            continue
