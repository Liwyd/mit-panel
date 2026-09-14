"""/start: superadmin menu, linkage check, main menu, the admin's panel list,
and a one-time heads-up to every superadmin the first time a given Telegram
user ever starts the bot."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import keyboards, texts
from backend.bot.filters import SuperadminFilter
from backend.bot.forecast import render
from backend.bot.nav import cancel_and_show_menu, forget_section, menu_kb_for
from backend.bot.panels import format_panel_line, safe_get_admins
from backend.bot.states import CreatePanel
from backend.bot import db
from backend.bot.config import bot_config as settings

router = Router(name="start")


async def _notify_superadmins_of_new_user(bot: Bot, message: Message, admins: list[dict]) -> None:
    user = message.from_user
    username = f"@{user.username}" if user.username else "—"
    if admins:
        text = texts.NEW_START_NOTIFICATION_LINKED.format(
            full_name=user.full_name,
            username=username,
            telegram_id=user.id,
            admin_username="، ".join(a["username"] for a in admins),
        )
    else:
        text = texts.NEW_START_NOTIFICATION_UNLINKED.format(
            full_name=user.full_name, username=username, telegram_id=user.id
        )
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id, text, reply_markup=keyboards.message_user_kb(user.id)
            )
        except Exception:
            continue


@router.message(CommandStart())
async def start(message: Message, bot: Bot) -> None:
    is_new_user = not db.user_exists(message.from_user.id)
    db.upsert_user(message.from_user.id, message.from_user.username, message.from_user.full_name)

    if message.from_user.id in settings.superadmin_id_list:
        # /start is a reset, so it also drops whichever section they were in.
        forget_section(message.from_user.id)
        await message.answer(texts.SUPERADMIN_WELCOME, reply_markup=keyboards.superadmin_menu_kb())
        return

    admins = await safe_get_admins(message)
    if admins is None:
        return
    if is_new_user:
        await _notify_superadmins_of_new_user(bot, message, admins)

    if not admins:
        await message.answer(
            texts.START_UNLINKED,
            reply_markup=await menu_kb_for(message.from_user.id),
        )
        return

    # Deliberately no volume figures here: with several panels a combined total
    # is meaningless, and per-panel numbers belong in «🗄 پنل‌های من».
    await message.answer(
        texts.START_LINKED.format(name=message.from_user.full_name),
        reply_markup=keyboards.main_menu_kb(),
    )


@router.message(F.text.in_({texts.BTN_MY_PANELS, texts.BTN_BALANCE}))
async def my_panels(message: Message) -> None:
    admins = await safe_get_admins(message)
    if admins is None:
        return
    if not admins:
        # Same button for everyone: with no panel it becomes the activation
        # screen, carrying the numeric ID they need to forward to support.
        await message.answer(
            texts.PANEL_ACTIVATION,
            reply_markup=keyboards.panel_request_kb(),
        )
        return
    text = texts.PANELS_LIST_HEADER + "".join(format_panel_line(a) for a in admins)
    await message.answer(text)


@router.message(F.text == texts.BTN_BACK)
async def back_to_menu(message: Message, state: FSMContext) -> None:
    """One Back for everyone: this router is registered first, so a copy in the
    superadmin router could never run. Dropping the remembered section is what
    makes it land on the root menu rather than back where it started."""
    await state.clear()
    forget_section(message.from_user.id)
    await message.answer(
        texts.BACK_TO_MENU, reply_markup=await menu_kb_for(message.from_user.id)
    )


@router.message(F.text == texts.BTN_FORECAST)
async def show_forecast(message: Message) -> None:
    admins = await safe_get_admins(message)
    if admins is None:
        return
    if not admins:
        await message.answer(texts.FORECAST_NO_PANELS)
        return
    for admin in admins:
        rendered = render(admin["username"], admin.get("traffic") or 0)
        if rendered is None:
            continue
        body, show_buy = rendered
        await message.answer(
            texts.FORECAST_TITLE + body,
            reply_markup=keyboards.topup_panel_kb(admin["username"]) if show_buy else None,
        )


@router.message(F.text == texts.BTN_CREATE_PANEL)
async def create_panel_stub(message: Message, state: FSMContext) -> None:
    if await SuperadminFilter()(message):
        await state.set_state(CreatePanel.name)
        await message.answer(texts.ASK_PANEL_NAME, reply_markup=keyboards.cancel_kb())
        return
    # Regular admin — redirect to shop flow (1 panel per account)
    from backend.bot import panel_client
    try:
        admins = await panel_client.get_admins(message.from_user.id)
    except Exception:
        admins = []
    if admins:
        await message.answer(texts.SHOP_ALREADY_HAS_PANEL)
        return
    # Redirect to shop: trigger the same flow as BTN_REQUEST_PANEL
    from backend.bot.routers.shop import request_panel_start
    await request_panel_start(message, state)


@router.message(F.text == texts.BTN_CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await cancel_and_show_menu(message, state)


@router.callback_query(F.data == "fj_check")
async def recheck_join(call: CallbackQuery) -> None:
    # ForceJoinMiddleware only lets this callback through once membership is
    # confirmed (or the gate is off), so reaching this handler already means OK.
    await call.answer(texts.FORCE_JOIN_CONFIRMED, show_alert=True)
