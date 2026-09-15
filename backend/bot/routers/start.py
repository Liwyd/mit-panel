"""/start: superadmin menu, linkage check, main menu, the admin's panel list,
and a one-time heads-up to every superadmin the first time a given Telegram
user ever starts the bot."""

from __future__ import annotations

import logging
import os
import tempfile

from aiogram import Bot, F, Router
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import keyboards, texts
from backend.bot import panel_client
from backend.bot.filters import SuperadminFilter
from backend.bot.forecast import render
from backend.bot.nav import cancel_and_show_menu, forget_section, menu_kb_for
from backend.bot.panels import format_panel_line, format_referral_panel_line, safe_get_admins
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

    # Fetch referral panels (purchased via this user's referral codes)
    try:
        referral_panels = await panel_client.get_referral_panels(message.from_user.id)
    except Exception:
        referral_panels = []

    if not admins and not referral_panels:
        # Same button for everyone: with no panel it becomes the activation
        # screen, carrying the numeric ID they need to forward to support.
        await message.answer(
            texts.PANEL_ACTIVATION,
            reply_markup=keyboards.panel_request_kb(),
        )
        return

    parts: list[str] = []
    if admins:
        parts.append(texts.PANELS_LIST_HEADER + "".join(format_panel_line(a) for a in admins))
    if referral_panels:
        parts.append(texts.REFERRAL_PANELS_HEADER + "".join(format_referral_panel_line(p) for p in referral_panels))
    await message.answer("".join(parts))


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


# ── Support button ────────────────────────────────────────────────────────

@router.message(F.text == texts.BTN_SUPPORT)
async def support_handler(message: Message) -> None:
    await message.answer(texts.SUPPORT_TEXT.format(user_id=message.from_user.id))


# ── Panel preview (collage) ──────────────────────────────────────────────

logger = logging.getLogger(__name__)

# Resolve image paths once at import time
_PANEL_PREVIEW_IMAGES: list[str] = []
for _name in ("loginpage.png", "panel.png"):
    _path = os.path.join(os.path.dirname(__file__), "..", "..", "..", _name)
    if os.path.isfile(_path):
        _PANEL_PREVIEW_IMAGES.append(_path)


def _make_collage(paths: list[str], max_width: int = 1200) -> str:
    """Create a side-by-side collage of 2 images. Returns temp file path."""
    from PIL import Image

    imgs = [Image.open(p) for p in paths]
    if len(imgs) == 1:
        # Single image: just resize
        img = imgs[0].copy()
        ratio = max_width / img.width
        img = img.resize((max_width, int(img.height * ratio)), Image.LANCZOS)
        out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
        img.save(out, "JPEG", quality=90)
        return out.name

    # Two images: place side by side
    h = max(img.height for img in imgs)
    resized = []
    for img in imgs:
        ratio = h / img.height
        new_w = int(img.width * ratio)
        new_h = int(img.height * ratio)
        # Limit each image to half the max width
        if new_w > max_width // 2:
            new_w = max_width // 2
            new_h = int(img.height * (new_w / img.width))
        resized.append(img.resize((new_w, new_h), Image.LANCZOS))

    total_w = sum(im.width for im in resized)
    canvas = Image.new("RGB", (total_w, h), (0, 0, 0))
    x = 0
    for im in resized:
        canvas.paste(im, (x, 0))
        x += im.width
    out = tempfile.NamedTemporaryFile(suffix=".jpg", delete=False)
    canvas.save(out, "JPEG", quality=90)
    return out.name


@router.message(F.text == texts.BTN_PANEL_PREVIEW)
async def panel_preview_handler(message: Message) -> None:
    if not _PANEL_PREVIEW_IMAGES:
        await message.answer("⚠️ تصاویر پنل یافت نشد.")
        return
    try:
        collage_path = _make_collage(_PANEL_PREVIEW_IMAGES)
        from aiogram.types import FSInputFile
        await message.answer_photo(
            photo=FSInputFile(collage_path),
            caption=texts.PANEL_PREVIEW_CAPTION,
        )
        try:
            os.unlink(collage_path)
        except OSError:
            pass
    except Exception:
        logger.exception("Failed to create panel preview collage")
        await message.answer("⚠️ خطا در نمایش تصویر پنل.")


# ── Referral code request ────────────────────────────────────────────────

@router.message(F.text == texts.BTN_REQUEST_REFERRAL)
async def referral_request_handler(message: Message, state: FSMContext, bot: Bot) -> None:
    if message.from_user.id in settings.superadmin_id_list:
        return

    # Check if user already has a pending request
    existing = db.get_pending_referral_request(message.from_user.id)
    if existing:
        await message.answer(texts.REFERRAL_REQUEST_ALREADY_PENDING)
        return

    # Check if user has a panel
    try:
        admins = await panel_client.get_admins(message.from_user.id)
    except Exception:
        admins = []

    if not admins:
        # User without panel — show benefits first with inline confirm
        from aiogram.utils.keyboard import InlineKeyboardBuilder
        kb = InlineKeyboardBuilder()
        kb.button(text="✅ بله، درخواست بده", callback_data="ref_req_confirm_no_panel")
        kb.button(text="❌ انصراف", callback_data="ref_req_cancel_no_panel")
        kb.adjust(2)
        await message.answer(
            texts.REFERRAL_BENEFITS_NO_PANEL,
            reply_markup=kb.as_markup(),
        )
        return

    # User has panel — create request directly
    db.create_referral_request(message.from_user.id, message.from_user.username)
    await message.answer(texts.REFERRAL_REQUEST_SUBMITTED)

    # Notify superadmins
    user = message.from_user
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id,
                texts.SUPERADMIN_REFERRAL_REQUEST.format(
                    username=user.username or "—",
                    user_id=user.id,
                    date=user.date.strftime("%Y-%m-%d %H:%M"),
                ),
                reply_markup=keyboards.referral_request_approval_kb(user.id),
            )
        except Exception:
            continue


@router.callback_query(F.data == "ref_req_confirm_no_panel")
async def referral_confirm_no_panel(call: CallbackQuery, bot: Bot) -> None:
    """User without panel confirms they want a referral code."""
    if call.from_user.id in settings.superadmin_id_list:
        await call.answer("⛔")
        return

    existing = db.get_pending_referral_request(call.from_user.id)
    if existing:
        await call.answer(texts.REFERRAL_REQUEST_ALREADY_PENDING, show_alert=True)
        return

    db.create_referral_request(call.from_user.id, call.from_user.username)
    await call.message.edit_text(texts.REFERRAL_REQUEST_SUBMITTED)

    user = call.from_user
    for superadmin_id in settings.superadmin_id_list:
        try:
            await bot.send_message(
                superadmin_id,
                texts.SUPERADMIN_REFERRAL_REQUEST.format(
                    username=user.username or "—",
                    user_id=user.id,
                    date=user.date.strftime("%Y-%m-%d %H:%M"),
                ),
                reply_markup=keyboards.referral_request_approval_kb(user.id),
            )
        except Exception:
            continue


@router.callback_query(F.data == "ref_req_cancel_no_panel")
async def referral_cancel_no_panel(call: CallbackQuery) -> None:
    await call.message.edit_text("❌ درخواست لغو شد.")


@router.callback_query(F.data.startswith("ref_req_approve:"))
async def referral_request_approve(call: CallbackQuery, state: FSMContext) -> None:
    if call.from_user.id not in settings.superadmin_id_list:
        await call.answer("⛔")
        return

    request_id = int(call.data.split(":")[1])

    # Get the request to find the user
    with db._connect() as conn:
        row = conn.execute(
            "SELECT * FROM referral_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()
    if not row:
        await call.answer("⚠️ درخواست یافت نشد", show_alert=True)
        return

    # Mark approved
    db.mark_referral_request_reviewed(request_id, "approved", call.from_user.id)
    await call.answer("✅ تأیید شد")

    # Now go to the normal referral code creation flow
    await state.update_data(ref_owner=row["telegram_id"])
    from backend.bot.states import ReferralManage
    await state.set_state(ReferralManage.code)
    await call.message.answer(
        texts.REFERRAL_ASK_CODE_STR,
        reply_markup=keyboards.cancel_kb(),
    )


@router.callback_query(F.data.startswith("ref_req_reject:"))
async def referral_request_reject(call: CallbackQuery) -> None:
    if call.from_user.id not in settings.superadmin_id_list:
        await call.answer("⛔")
        return

    request_id = int(call.data.split(":")[1])

    # Get the request to find the user
    with db._connect() as conn:
        row = conn.execute(
            "SELECT * FROM referral_requests WHERE id = ? AND status = 'pending'",
            (request_id,),
        ).fetchone()
    if not row:
        await call.answer("⚠️ درخواست یافت نشد", show_alert=True)
        return

    # Mark rejected
    db.mark_referral_request_reviewed(request_id, "rejected", call.from_user.id)
    await call.answer("❌ رد شد")

    # Notify the user
    try:
        await call.bot.send_message(
            row["telegram_id"],
            texts.REFERRAL_REQUEST_REJECTED_NOTIFY.format(reason="درخواست شما توسط مدیریت رد شد."),
        )
    except Exception:
        pass
