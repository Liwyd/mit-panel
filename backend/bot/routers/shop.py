"""Shop mode: lets anyone start the bot and purchase a panel.

Handles the full lifecycle:
  1. Prospect taps "Request Panel" → pick panel → pick traffic → referral code → receipt
  2. Superadmin sees request → approves / rejects
  3. On approval: create admin, link telegram_id, grant referral bonus, notify buyer
"""

from __future__ import annotations

import logging
import os
import uuid

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import db, keyboards, texts
from backend.bot import panel_client
from backend.bot.config import bot_config as settings
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import ALL_MENU_TEXTS, menu_kb_for
from backend.bot.states import ShopBuy, ShopApprove

logger = logging.getLogger(__name__)

router = Router(name="shop")


# ── helpers ────────────────────────────────────────────────────────────────

def _price_for_shop(panel_name: str, referral_code_id: int | None = None) -> float:
    """Compute per-GB price for a shop purchase."""
    if referral_code_id:
        row = db.get_referral_code_by_owner(None)  # dummy — caller passes resolved price
    return db.get_effective_price(panel_name)


def _resolve_price(panel_name: str, referral_code_id: int | None = None) -> float:
    """Return the per-GB price, using the referral code's price if applicable."""
    if referral_code_id:
        with db._connect() as conn:
            row = conn.execute(
                "SELECT price_per_gb FROM referral_codes WHERE id = ?", (referral_code_id,)
            ).fetchone()
            if row:
                return float(row["price_per_gb"])
    return db.get_effective_price(panel_name)


# ── 1. Request Panel button ───────────────────────────────────────────────

@router.message(F.text == texts.BTN_REQUEST_PANEL)
async def request_panel_start(message: Message, state: FSMContext) -> None:
    # Block superadmins — they use the admin flow
    if message.from_user.id in settings.superadmin_id_list:
        return

    # 1 panel per account limit
    try:
        existing_panels = await panel_client.get_admins(message.from_user.id)
    except Exception:
        existing_panels = []
    if existing_panels:
        await message.answer(texts.SHOP_ALREADY_HAS_PANEL)
        return

    # Check for existing pending request
    existing = db.get_panel_request(message.from_user.id)
    if existing and existing.get("status") == "pending":
        await message.answer(texts.SHOP_ALREADY_PENDING)
        return

    # List available Marzban panels
    panels = await _list_marzban_panels()
    if not panels:
        await message.answer(texts.NO_MARZBAN_PANELS)
        return

    await state.set_state(ShopBuy.panel)
    await state.update_data(shop_panels=panels)
    await message.answer(
        texts.SHOP_ASK_PANEL,
        reply_markup=keyboards.shop_panel_kb(panels),
    )


async def _list_marzban_panels() -> list[str]:
    from backend.bot import panel_client
    try:
        return await panel_client.list_panels()
    except Exception:
        return []


# ── 2. Panel picked ──────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("shop_panel:"))
async def shop_pick_panel(call: CallbackQuery, state: FSMContext) -> None:
    if call.from_user.id in settings.superadmin_id_list:
        await call.answer()
        return

    panel_name = call.data.split(":", 1)[1]
    await state.update_data(shop_panel=panel_name)
    await state.set_state(ShopBuy.amount_gb)
    await call.answer()
    await call.message.answer(
        texts.SHOP_ASK_TRAFFIC,
        reply_markup=keyboards.shop_amount_kb(),
    )


# ── 3. Amount picked ────────────────────────────────────────────────────

@router.callback_query(F.data.startswith("shop_gb:"), ShopBuy.amount_gb)
async def shop_pick_amount_gb(call: CallbackQuery, state: FSMContext) -> None:
    choice = call.data.split(":", 1)[1]
    if choice == "custom":
        await call.answer()
        await call.message.answer(texts.SHOP_CUSTOM_AMOUNT)
        return
    gb = float(choice)
    await state.update_data(shop_gb=gb)
    await _ask_referral_code(call.message, state)
    await call.answer()


@router.message(ShopBuy.amount_gb, ~F.text.in_(ALL_MENU_TEXTS))
async def shop_get_amount_text(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        gb = float(raw)
        if gb <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_AMOUNT_GB)
        return
    await state.update_data(shop_gb=gb)
    await _ask_referral_code(message, state)


# ── 4. Referral code ────────────────────────────────────────────────────

async def _ask_referral_code(message: Message, state: FSMContext) -> None:
    await state.set_state(ShopBuy.referral_code)
    await message.answer(
        texts.REFERRAL_ASK_CODE,
        reply_markup=keyboards.referral_skip_kb(),
    )


@router.callback_query(F.data == "shop_skip_referral", ShopBuy.referral_code)
async def shop_skip_referral(call: CallbackQuery, state: FSMContext) -> None:
    await state.update_data(shop_referral_code_id=None)
    await call.answer()
    await _ask_username(call.message, state)


@router.message(ShopBuy.referral_code, ~F.text.in_(ALL_MENU_TEXTS))
async def shop_get_referral_code(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()

    # Skip
    if not raw or raw == texts.BTN_SKIP:
        await state.update_data(shop_referral_code_id=None)
        await _ask_username(message, state)
        return

    code_row = db.get_referral_code(raw)
    if not code_row:
        await message.answer(texts.REFERRAL_INVALID)
        return

    await state.update_data(shop_referral_code_id=code_row["id"])
    price = code_row["price_per_gb"]
    await message.answer(texts.REFERRAL_APPLIED.format(price=int(price)))
    await _ask_username(message, state)


# ── 5. Username ─────────────────────────────────────────────────────────

async def _ask_username(message: Message, state: FSMContext) -> None:
    await state.set_state(ShopBuy.username)
    await message.answer(texts.SHOP_ASK_USERNAME, reply_markup=keyboards.cancel_kb())


@router.message(ShopBuy.username, ~F.text.in_(ALL_MENU_TEXTS))
async def shop_get_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.SHOP_ASK_USERNAME)
        return

    # Check if username is already taken in Marzban
    try:
        from backend.bot import panel_client
        panels = await panel_client.list_panels()
        if panels:
            from backend.services.marzban.api import APIService as MarzbanAPI
            from backend.db.engin import sessionLocal
            from backend.db import crud
            with sessionLocal() as db_session:
                panel_obj = crud.get_panel_by_name(db_session, panels[0])
            if panel_obj:
                sudo_api = MarzbanAPI(
                    url=panel_obj.url, username=panel_obj.username, password=panel_obj.password
                )
                existing = await sudo_api.get_user(username)
                # Marzban returns {"detail": "User not found"} for non-existent users
                if existing and isinstance(existing, dict) and "username" in existing:
                    await message.answer(texts.SHOP_USERNAME_TAKEN)
                    return
    except Exception:
        pass  # If Marzban check fails, allow the username

    await state.update_data(shop_username=username)
    await _ask_password(message, state)


# ── 6. Password ────────────────────────────────────────────────────────

def _is_strong_password(pw: str) -> bool:
    if len(pw) < 8:
        return False
    has_letter = any(c.isalpha() for c in pw)
    has_digit = any(c.isdigit() for c in pw)
    return has_letter and has_digit


async def _ask_password(message: Message, state: FSMContext) -> None:
    await state.set_state(ShopBuy.password)
    await message.answer(texts.SHOP_ASK_PASSWORD, reply_markup=keyboards.cancel_kb())


@router.message(ShopBuy.password, ~F.text.in_(ALL_MENU_TEXTS))
async def shop_get_password(message: Message, state: FSMContext) -> None:
    password = (message.text or "").strip()
    if not _is_strong_password(password):
        await message.answer(texts.SHOP_PASSWORD_WEAK)
        return

    await state.update_data(shop_password=password)
    await _show_invoice(message, state)


# ── 5. Show invoice ──────────────────────────────────────────────────────

async def _show_invoice(message: Message, state: FSMContext) -> None:
    try:
        data = await state.get_data()
        panel_name = data["shop_panel"]
        gb = data["shop_gb"]
        referral_code_id = data.get("shop_referral_code_id")
        price_per_gb = _resolve_price(panel_name, referral_code_id)
        total = int(gb * price_per_gb)

        if total <= 0:
            await message.answer(
                texts.PRICE_NOT_SET,
                reply_markup=await menu_kb_for(message.from_user.id),
            )
            await state.clear()
            return

        await state.update_data(shop_total=total)
        await state.set_state(ShopBuy.receipt)

        card = db.get_setting("card_number") or ""
        if card:
            await message.answer(
                texts.SHOP_PANEL_INFO.format(panel=panel_name, gb=gb, price=total),
            )
            await message.answer(
                texts.SHOP_CARD_INSTRUCTIONS.format(card=card, price=total),
            )
            await message.answer(texts.SHOP_RECEIPT_PROMPT)
        else:
            await message.answer(texts.CARD_NOT_CONFIGURED)
            await state.clear()
    except Exception as exc:
        logger.error("_show_invoice crashed: %s", exc, exc_info=True)
        await state.clear()
        try:
            await message.answer(
                "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.",
                reply_markup=keyboards.cancel_kb(),
            )
        except Exception:
            pass


# ── 6. Receipt received ──────────────────────────────────────────────────

@router.message(ShopBuy.receipt)
async def shop_get_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    try:
        data = await state.get_data()
        await state.clear()

        panel_name = data["shop_panel"]
        gb = data["shop_gb"]
        referral_code_id = data.get("shop_referral_code_id")
        desired_username = data.get("shop_username")
        desired_password = data.get("shop_password")

        # Download receipt
        photo = message.photo[-1]
        ext = "jpg"
        filename = f"shop_{message.from_user.id}_{uuid.uuid4().hex[:8]}.{ext}"
        media_dir = settings.media_dir
        os.makedirs(media_dir, exist_ok=True)
        receipt_path = os.path.join(media_dir, filename)
        await bot.download(photo, destination=receipt_path)

        # Create panel request
        request_id = db.create_panel_request(
            telegram_id=message.from_user.id,
            panel_name=panel_name,
            traffic_gb=gb,
            receipt_path=receipt_path,
            referral_code_id=referral_code_id,
            desired_username=desired_username,
            desired_password=desired_password,
        )

        await message.answer(
            texts.SHOP_REQUEST_SUBMITTED,
            reply_markup=await menu_kb_for(message.from_user.id),
        )

        # Notify superadmins — send the receipt photo with approval buttons
        price_per_gb = _resolve_price(panel_name, referral_code_id)
        total = int(gb * price_per_gb)
        username = message.from_user.username or ""
        caption = (
            texts.PANEL_REQUEST_HEADER.format(
                username=username, telegram_id=message.from_user.id
            )
            + "\n\n"
            + texts.PANEL_REQUEST_INFO.format(panel=panel_name, gb=gb, price=total)
        )
        for sid in settings.superadmin_id_list:
            try:
                await bot.send_photo(
                    sid,
                    photo=photo.file_id,
                    caption=caption,
                    reply_markup=keyboards.panel_request_approval_kb(request_id),
                )
            except Exception as exc:
                logger.error(
                    "Failed to notify superadmin %s of shop request: %s",
                    sid, exc,
                )
    except Exception as exc:
        logger.error("shop_get_receipt crashed: %s", exc, exc_info=True)
        try:
            await message.answer(
                "❌ خطایی رخ داد. لطفاً دوباره تلاش کنید.",
                reply_markup=await menu_kb_for(message.from_user.id),
            )
        except Exception:
            pass


# ── 7. Superadmin approves ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("panel_req_approve:"))
async def panel_request_approve(call: CallbackQuery, bot: Bot) -> None:
    if call.from_user.id not in settings.superadmin_id_list:
        await call.answer("Unauthorized", show_alert=True)
        return

    request_id = int(call.data.split(":", 1)[1])
    req = db.get_panel_request(request_id)
    if not req or req["status"] != "pending":
        await call.answer(texts.ALREADY_HANDLED, show_alert=True)
        return

    await call.answer()

    # Use user-provided credentials
    username = req.get("desired_username") or f"shop_{req['telegram_id']}"
    password = req.get("desired_password") or uuid.uuid4().hex[:12]

    try:
        from backend.bot import panel_client

        result = await panel_client.create_admin_for_shop(
            username=username,
            password=password,
            panel=req["panel_name"],
            traffic_gb=req["traffic_gb"],
            telegram_id=req["telegram_id"],
        )
    except Exception as exc:
        logger.error(f"Shop panel creation failed for request {request_id}: {exc}")
        await call.message.answer(f"❌ Failed to create panel: {exc}")
        return

    # Mark approved
    db.mark_panel_request_reviewed(request_id, "approved", call.from_user.id)
    db.ensure_user(req["telegram_id"])
    db.set_user_linked(req["telegram_id"], True)

    # Panel link
    panel_url = settings.panel_link_url

    # Send credentials to buyer + full menu (transition from prospect to linked)
    creds_text = texts.SHOP_REQUEST_APPROVED.format(
        url=panel_url, username=username, password=password
    )
    try:
        await bot.send_message(
            req["telegram_id"],
            creds_text,
            reply_markup=keyboards.main_menu_kb(),
        )
    except Exception:
        logger.error(f"Failed to send credentials to buyer {req['telegram_id']}")

    # Send credentials to superadmin
    await call.message.answer(
        texts.PANEL_LINK_INFO.format(url=panel_url, username=username, password=password)
    )

    # Referral bonus
    referral_code_id = req.get("referral_code_id")
    if referral_code_id:
        with db._connect() as conn:
            code_row = conn.execute(
                "SELECT bonus_percent, owner_telegram_id FROM referral_codes WHERE id = ?",
                (referral_code_id,),
            ).fetchone()
        if code_row:
            bonus_gb = round(req["traffic_gb"] * code_row["bonus_percent"] / 100, 2)
            owner_tid = code_row["owner_telegram_id"]
            if owner_tid and bonus_gb > 0:
                # Record usage
                db.create_referral_usage(
                    code_id=referral_code_id,
                    buyer_tg_id=req["telegram_id"],
                    buyer_username=username,
                    traffic_gb=req["traffic_gb"],
                    bonus_gb=bonus_gb,
                )
                # Grant bonus to referrer
                try:
                    from backend.bot import panel_client
                    referrer_panels = await panel_client.get_admins(owner_tid)
                    if referrer_panels:
                        referrer_username = referrer_panels[0]["username"]
                        await panel_client.topup_by_username(referrer_username, bonus_gb)
                        await bot.send_message(
                            owner_tid,
                            texts.REFERRAL_BONUS_NOTIFY.format(gb=bonus_gb, user=username),
                        )
                except Exception as exc:
                    logger.error(f"Referral bonus grant failed: {exc}")

    # Remove approval buttons
    try:
        await call.message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── 8. Superadmin rejects ───────────────────────────────────────────────

@router.callback_query(F.data.startswith("panel_req_reject:"))
async def panel_request_reject_start(call: CallbackQuery, state: FSMContext) -> None:
    if call.from_user.id not in settings.superadmin_id_list:
        await call.answer("Unauthorized", show_alert=True)
        return

    request_id = int(call.data.split(":", 1)[1])
    req = db.get_panel_request(request_id)
    if not req or req["status"] != "pending":
        await call.answer(texts.ALREADY_HANDLED, show_alert=True)
        return

    await state.update_data(reject_request_id=request_id)
    await state.set_state(ShopApprove.reason)
    await call.answer()
    await call.message.answer(texts.ASK_REJECT_REASON)


@router.message(ShopApprove.reason, ~F.text.in_(ALL_MENU_TEXTS))
async def panel_request_reject_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    request_id = data["reject_request_id"]
    reason = (message.text or "").strip()
    await state.clear()

    req = db.get_panel_request(request_id)
    if not req or req["status"] != "pending":
        await message.answer(texts.ALREADY_HANDLED)
        return

    db.mark_panel_request_reviewed(request_id, "rejected", message.from_user.id, reason or None)

    # Notify buyer
    try:
        await bot.send_message(
            req["telegram_id"],
            texts.SHOP_REQUEST_REJECTED.format(reason=reason or "بدون علت"),
        )
    except Exception:
        pass

    await message.answer(texts.PANEL_REQUEST_REJECTED)

    # Remove approval buttons — find original message by scanning pending
    try:
        await message.edit_reply_markup(reply_markup=None)
    except Exception:
        pass


# ── 9. My Referral Code ─────────────────────────────────────────────────

@router.message(F.text == texts.BTN_MY_REFERRAL)
async def my_referral_code(message: Message) -> None:
    if message.from_user.id in settings.superadmin_id_list:
        return

    existing = db.get_referral_code_by_owner(message.from_user.id)
    if existing:
        await message.answer(texts.REFERRAL_CODE_EXISTS.format(code=existing["code"]))
    else:
        await message.answer(texts.REFERRAL_NO_CODE)


# ── 10. List pending panel requests (superadmin) ────────────────────────

@router.message(F.text == texts.BTN_PENDING_REQUESTS)
async def list_pending_panel_requests(message: Message, bot: Bot) -> None:
    if message.from_user.id not in settings.superadmin_id_list:
        return

    # Also list shop requests alongside regular topup requests
    shop_requests = db.list_pending_panel_requests()
    for req in shop_requests:
        username = req.get("username") or str(req["telegram_id"])
        price_per_gb = db.get_effective_price(req["panel_name"])
        total = int(req["traffic_gb"] * price_per_gb)
        caption = (
            texts.PANEL_REQUEST_HEADER.format(username=username, telegram_id=req["telegram_id"])
            + "\n\n"
            + texts.PANEL_REQUEST_INFO.format(
                panel=req["panel_name"], gb=req["traffic_gb"], price=total
            )
        )
        receipt_path = req.get("receipt_path")
        if receipt_path and os.path.isfile(receipt_path):
            from aiogram.types import FSInputFile
            try:
                await bot.send_photo(
                    message.from_user.id,
                    photo=FSInputFile(receipt_path),
                    caption=caption,
                    reply_markup=keyboards.panel_request_approval_kb(req["id"]),
                )
                continue
            except Exception:
                pass
        # Fallback: text only
        await message.answer(
            caption,
            reply_markup=keyboards.panel_request_approval_kb(req["id"]),
        )
