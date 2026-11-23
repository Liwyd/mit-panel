"""The Black Friday section: packages, settling debt at the event rate, stats.

Works like the normal top-up (شارژ حجم) with its own rules: only a card receipt
or the wallet, never delayed or consumption credit, and nothing can be bought
while a bill is open. It has its own FSM group (states.BlackFriday) and its own
callback prefixes (`bf_*`) so none of the TopUp payment handlers can ever see a
Black Friday quote.
"""

from __future__ import annotations

import html
import logging
import os
import uuid
from dataclasses import asdict

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, FSInputFile, Message

from backend.bot import (
    approvals, auto_approve, black_friday, db, keyboards, notify, panel_client, texts, validation,
)
from backend.bot.config import bot_config as settings
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import ALL_MENU_TEXTS, menu_kb_for, superadmin_kb
from backend.bot.panel_client import PanelClientError
from backend.bot.panels import owned_panel, safe_get_admins
from backend.bot.routers.topup import _in_flight_payments
from backend.bot.states import BlackFriday
from backend.bot.units import bytes_to_gb

router = Router(name="black_friday")

logger = logging.getLogger(__name__)

_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")


# ---- entry ---------------------------------------------------------------------

async def _enter(message: Message, state: FSMContext, user_id: int) -> None:
    """Open the section for `user_id`. `message` is only where replies go: for a
    button on a bot message it was sent by the bot, hence the explicit id."""
    await state.clear()
    if not black_friday.is_active():
        await message.answer(texts.BF_ENDED, reply_markup=await menu_kb_for(user_id))
        return

    admins = await safe_get_admins(message, user_id)
    if admins is None:
        return
    # A superadmin has no use for buying a panel through the shop; they keep
    # getting the "no panel" notice they always did.
    if not admins and user_id in settings.superadmin_id_list:
        await message.answer(texts.NOT_LINKED_RETRY, reply_markup=await menu_kb_for(user_id))
        return

    # Debt comes first, whichever panel it is on: someone owing money has no use
    # for a package list they cannot buy from.
    if black_friday.has_open_bills(user_id):
        await _show_items(message, user_id)
        return

    # Everyone sees the packages, panel or not; where the volume goes is asked
    # after they have chosen it.
    await _show_packages(message, state)


@router.message(F.text == texts.BTN_BLACK_FRIDAY)
async def open_from_menu(message: Message, state: FSMContext) -> None:
    await _enter(message, state, message.from_user.id)


@router.callback_query(F.data == "bf_open")
async def open_from_button(call: CallbackQuery, state: FSMContext) -> None:
    await call.answer()
    await _enter(call.message, state, call.from_user.id)


@router.callback_query(F.data.startswith("pick:bf:"))
async def picked_panel(call: CallbackQuery, state: FSMContext) -> None:
    username = call.data.split(":", 2)[2]
    if not await owned_panel(call.from_user.id, username):
        await call.answer(texts.NOT_LINKED_RETRY, show_alert=True)
        return
    await call.answer()
    if not black_friday.is_active():
        await call.message.answer(texts.BF_ENDED, reply_markup=await menu_kb_for(call.from_user.id))
        return
    if black_friday.has_open_bills(call.from_user.id):
        await _show_items(call.message, call.from_user.id)
        return
    await _show_packages(call.message, state)


# ---- debt first ------------------------------------------------------------------

def _saving_part(saving: int) -> str:
    if saving > 0:
        return texts.BF_ITEM_SAVING_PART.format(saving=saving)
    return texts.BF_ITEM_NO_SAVING_PART


async def _show_items(message: Message, user_id: int) -> None:
    items = black_friday.open_items(user_id)
    lines = ""
    for item in items:
        if item.kind == "debt":
            lines += texts.BF_ITEM_DEBT.format(
                username=html.escape(item.ref), original=item.original,
                discounted=item.discounted, saving_part=_saving_part(item.saving),
            )
        else:
            panel_part = (
                texts.BF_ITEM_PANEL_PART.format(panel=html.escape(item.panel)) if item.panel else ""
            )
            lines += texts.BF_ITEM_INVOICE.format(
                id=item.ref, panel_part=panel_part, original=item.original,
                discounted=item.discounted, saving_part=_saving_part(item.saving),
            )
    await message.answer(
        texts.BF_BLOCKED_BY_DEBT.format(items=lines),
        reply_markup=keyboards.bf_items_kb(items) if items else None,
    )


def _item_screen(bf: dict) -> tuple[str, str]:
    """(subject, saving line) for the pay screen of a debt or an invoice."""
    if bf["kind"] == "debt":
        subject = texts.BF_SUBJECT_DEBT.format(username=html.escape(bf["username"]))
    else:
        subject = texts.BF_SUBJECT_INVOICE.format(id=bf["invoice_id"])
    saving = bf["original"] - bf["discounted"]
    return subject, (texts.BF_SAVING_LINE.format(saving=saving) if saving > 0 else "")


async def _send_item_screen(message: Message, state: FSMContext, bf: dict) -> None:
    await state.update_data(bf=bf)
    await state.set_state(BlackFriday.awaiting_payment)
    subject, saving_line = _item_screen(bf)
    await message.answer(
        texts.BF_PAY_ITEM.format(
            subject=subject, original=bf["original"], discounted=bf["discounted"],
            saving_line=saving_line,
        ),
        reply_markup=keyboards.bf_payment_methods_kb(),
    )


def _debt_bf(user_id: int, username: str) -> dict | None:
    """The quote for one debt, or None if it is not this person's or is gone."""
    record = db.get_debt_record(username)
    if not record or record["amount"] <= 0 or record["telegram_id"] != user_id:
        return None
    original, discounted, _ = black_friday.debt_quote(username)
    if original <= 0:
        return None
    return {"kind": "debt", "username": username, "original": original, "discounted": discounted}


def _invoice_bf(user_id: int, invoice_id: int) -> dict | None:
    invoice = db.get_invoice(invoice_id)
    if invoice is None or invoice.telegram_id != user_id or invoice.status != "pending":
        return None
    original, discounted, _ = black_friday.invoice_quote(invoice)
    return {
        "kind": "invoice", "invoice_id": invoice.id, "original": original, "discounted": discounted,
    }


@router.callback_query(F.data.startswith("bf_item:"))
async def pick_item(call: CallbackQuery, state: FSMContext) -> None:
    # bf_item:d:<panel> or bf_item:i:<invoice id>; the client wrote it, so it is
    # checked against who is asking before anything is shown.
    try:
        _, which, ref = call.data.split(":", 2)
    except ValueError:
        await call.answer(texts.BF_ITEM_GONE, show_alert=True)
        return
    if not black_friday.is_active():
        await call.answer()
        await call.message.answer(texts.BF_ENDED, reply_markup=await menu_kb_for(call.from_user.id))
        return
    if which == "d":
        bf = _debt_bf(call.from_user.id, ref)
    elif which == "i" and ref.isdigit():
        bf = _invoice_bf(call.from_user.id, int(ref))
    else:
        bf = None
    if bf is None:
        await call.answer(texts.BF_ITEM_GONE, show_alert=True)
        return
    await call.answer()
    await _send_item_screen(call.message, state, bf)


# ---- packages --------------------------------------------------------------------

async def _show_packages(message: Message, state: FSMContext) -> None:
    """The public terms: priced with no panel (the global price), because the
    panel the volume goes to is only chosen afterwards."""
    quotes = [black_friday.package_quote("", float(paid)) for paid, _ in black_friday.PACKAGES]
    await state.set_state(BlackFriday.choosing)
    await message.answer(
        texts.BF_MENU_INTRO_PUBLIC.format(
            price=black_friday.bf_price(""),
            gift_note=texts.BF_GIFT_NOTE if black_friday.gift_eligible("") else texts.BF_NO_GIFT_NOTE,
        ),
        reply_markup=keyboards.bf_packages_kb(quotes),
    )


async def _gate(message: Message, state: FSMContext, user_id: int) -> bool:
    """Whether the event is still on and nothing is owed; otherwise says why."""
    if not black_friday.is_active():
        await state.clear()
        await message.answer(texts.BF_ENDED, reply_markup=await menu_kb_for(user_id))
        return False
    if black_friday.has_open_bills(user_id):
        await state.clear()
        await _show_items(message, user_id)
        return False
    return True


def _quote_for(username: str, selection: dict) -> black_friday.Quote | None:
    """The quote for the chosen volume at one panel's price ("" is the public
    price, used for a new panel)."""
    if selection["kind"] == "pkg":
        return black_friday.package_quote(username, selection["paid_gb"])
    return black_friday.custom_quote(username, selection["paid_gb"])


async def _show_quote(
    message: Message, state: FSMContext, username: str, quote: black_friday.Quote
) -> None:
    await state.update_data(
        panel_username=username, bf={"kind": "topup", "panel_username": username, "quote": asdict(quote)}
    )
    await state.set_state(BlackFriday.awaiting_payment)
    await message.answer(
        texts.BF_QUOTE.format(
            username=html.escape(username),
            paid_gb=quote.paid_gb,
            gift_line=texts.BF_GIFT_LINE.format(gift_gb=quote.gift_gb) if quote.gift_gb else "",
            granted_gb=quote.granted_gb,
            total=quote.total,
            saving_line=texts.BF_SAVING_LINE.format(saving=quote.saving) if quote.saving > 0 else "",
        ),
        reply_markup=keyboards.bf_payment_methods_kb(),
    )


@router.callback_query(F.data.startswith("bf_pkg:"), BlackFriday.choosing)
async def pick_package(call: CallbackQuery, state: FSMContext) -> None:
    choice = call.data.split(":", 1)[1]
    user_id = call.from_user.id

    if not black_friday.is_active() or black_friday.has_open_bills(user_id):
        await call.answer()
        await _gate(call.message, state, user_id)
        return

    if choice == "custom":
        await call.answer()
        await state.set_state(BlackFriday.custom_amount)
        await call.message.answer(
            texts.BF_ASK_CUSTOM.format(
                min_gb=black_friday.CUSTOM_MIN_GB, max_gb=black_friday.CUSTOM_MAX_GB
            ),
            reply_markup=keyboards.cancel_kb(),
        )
        return

    selection = {"kind": "pkg", "paid_gb": float(choice)} if choice.isdigit() else None
    if selection is None or _quote_for("", selection) is None:
        await call.answer(texts.BF_NOT_AVAILABLE, show_alert=True)
        return
    await call.answer()
    await _ask_target(call.message, state, user_id, selection)


@router.message(BlackFriday.custom_amount, ~F.text.in_(ALL_MENU_TEXTS))
async def get_custom_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().translate(_PERSIAN_DIGITS).replace(",", "")
    try:
        amount = float(raw)
    except ValueError:
        amount = None
    if amount is None or amount != amount or amount <= 0 or amount == float("inf"):
        await message.answer(texts.BF_CUSTOM_INVALID)
        return

    selection = {"kind": "custom", "paid_gb": amount}
    if _quote_for("", selection) is None:
        await message.answer(
            texts.BF_CUSTOM_OUT_OF_RANGE.format(
                min_gb=black_friday.CUSTOM_MIN_GB, max_gb=black_friday.CUSTOM_MAX_GB
            )
        )
        return

    user_id = message.from_user.id
    if not await _gate(message, state, user_id):
        return
    await _ask_target(message, state, user_id, selection)


# ---- where the volume goes ------------------------------------------------------------

async def _ask_target(
    message: Message, state: FSMContext, user_id: int, selection: dict
) -> None:
    """Their own panels plus a new one; with no panel the only choice is a new one,
    so that question is skipped."""
    await state.update_data(bf_sel=selection)
    admins = await safe_get_admins(message, user_id)
    if admins is None:
        return
    if not admins:
        await _start_new_panel(message, state, user_id)
        return
    metadata = db.list_panel_metadata(user_id)
    panels = [
        (admin["username"], metadata.get(admin["username"], {}).get("panel_number"))
        for admin in admins
    ]
    await state.set_state(BlackFriday.choosing_target)
    await message.answer(texts.BF_ASK_TARGET, reply_markup=keyboards.bf_target_kb(panels))


@router.callback_query(F.data.startswith("bf_target:"), BlackFriday.choosing_target)
async def pick_target(call: CallbackQuery, state: FSMContext) -> None:
    user_id = call.from_user.id
    selection = (await state.get_data()).get("bf_sel")
    # bf_target:new or bf_target:p:<panel>; the client wrote it.
    parts = call.data.split(":", 2)
    if not selection or len(parts) < 2 or parts[1] not in ("new", "p"):
        await call.answer(texts.BF_NOT_AVAILABLE, show_alert=True)
        return
    if not black_friday.is_active() or black_friday.has_open_bills(user_id):
        await call.answer()
        await _gate(call.message, state, user_id)
        return

    if parts[1] == "new":
        await call.answer()
        await _start_new_panel(call.message, state, user_id)
        return

    username = parts[2] if len(parts) == 3 else ""
    try:
        owned = await owned_panel(user_id, username) if username else None
    except Exception as exc:
        logger.error("panel lookup failed for %s: %s", user_id, exc)
        await call.answer(texts.PANEL_UNREACHABLE, show_alert=True)
        return
    if not owned:
        await call.answer(texts.NOT_LINKED_RETRY, show_alert=True)
        return
    quote = _quote_for(username, selection)
    if quote is None:
        await call.answer(texts.BF_NOT_AVAILABLE, show_alert=True)
        return
    await call.answer()
    await _show_quote(call.message, state, username, quote)


# ---- a new panel ---------------------------------------------------------------------

async def _list_servers() -> list[str]:
    try:
        return await panel_client.list_panels()
    except Exception as exc:
        logger.warning("could not list the panel servers: %s", exc)
        return []


async def _username_taken(username: str) -> bool:
    # Same as the shop: a failed lookup is not a reason to turn the buyer away.
    try:
        return await panel_client.check_username_taken(username)
    except Exception:
        return False


async def _start_new_panel(message: Message, state: FSMContext, user_id: int) -> None:
    if db.get_pending_panel_request(user_id):
        await state.clear()
        await message.answer(texts.SHOP_ALREADY_PENDING, reply_markup=await menu_kb_for(user_id))
        return
    servers = await _list_servers()
    if not servers:
        await state.clear()
        await message.answer(texts.NO_MARZBAN_PANELS, reply_markup=await menu_kb_for(user_id))
        return
    if len(servers) == 1:
        await _ask_new_username(message, state, servers[0])
        return
    await state.set_state(BlackFriday.new_server)
    await message.answer(texts.BF_ASK_NEW_SERVER, reply_markup=keyboards.bf_server_kb(servers))


@router.callback_query(F.data.startswith("bf_srv:"), BlackFriday.new_server)
async def pick_server(call: CallbackQuery, state: FSMContext) -> None:
    server = call.data.split(":", 1)[1]
    # The name came from the client: it must be one of the real servers.
    if server not in await _list_servers():
        await call.answer(texts.BF_NOT_AVAILABLE, show_alert=True)
        return
    await call.answer()
    await _ask_new_username(call.message, state, server)


async def _ask_new_username(message: Message, state: FSMContext, server: str) -> None:
    await state.update_data(bf_new_server=server)
    await state.set_state(BlackFriday.new_username)
    await message.answer(texts.SHOP_ASK_USERNAME, reply_markup=keyboards.cancel_kb())


@router.message(BlackFriday.new_username, ~F.text.in_(ALL_MENU_TEXTS))
async def get_new_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip().lower()
    if not username:
        await message.answer(texts.SHOP_ASK_USERNAME)
        return
    if validation.has_space(username):
        await message.answer(texts.USERNAME_NO_SPACE, reply_markup=keyboards.cancel_kb())
        return
    if await _username_taken(username):
        await message.answer(texts.SHOP_USERNAME_TAKEN)
        return
    await state.update_data(bf_new_username=username)
    await state.set_state(BlackFriday.new_password)
    await message.answer(texts.SHOP_ASK_PASSWORD, reply_markup=keyboards.cancel_kb())


@router.message(BlackFriday.new_password, ~F.text.in_(ALL_MENU_TEXTS))
async def get_new_password(message: Message, state: FSMContext) -> None:
    password = (message.text or "").strip()
    if not validation.is_strong_password(password):
        await message.answer(texts.SHOP_PASSWORD_WEAK)
        return

    data = await state.get_data()
    selection = data.get("bf_sel")
    quote = _quote_for("", selection) if selection else None
    if quote is None or not data.get("bf_new_server") or not data.get("bf_new_username"):
        await state.clear()
        await message.answer(
            texts.BF_NOT_AVAILABLE, reply_markup=await menu_kb_for(message.from_user.id)
        )
        return
    bf = {
        "kind": "new_panel", "selection": selection, "server": data["bf_new_server"],
        "username": data["bf_new_username"], "password": password, "quote": asdict(quote),
    }
    await _show_new_quote(message, state, bf)


async def _show_new_quote(message: Message, state: FSMContext, bf: dict) -> None:
    quote = black_friday.Quote(**bf["quote"])
    await state.update_data(bf=bf)
    await state.set_state(BlackFriday.awaiting_payment)
    await message.answer(
        texts.BF_NEW_QUOTE.format(
            server=html.escape(bf["server"]),
            username=html.escape(bf["username"]),
            paid_gb=quote.paid_gb,
            gift_line=texts.BF_GIFT_LINE.format(gift_gb=quote.gift_gb) if quote.gift_gb else "",
            granted_gb=quote.granted_gb,
            total=quote.total,
            saving_line=texts.BF_SAVING_LINE.format(saving=quote.saving) if quote.saving > 0 else "",
        ),
        reply_markup=keyboards.bf_payment_methods_kb(),
    )


# ---- checks that run again at the moment of payment ---------------------------------

async def _revalidate(message: Message, state: FSMContext, user_id: int, bf: dict) -> bool:
    """Whether the quote the customer is about to pay is still true.

    The menu check is not a gate: debt may have appeared, a price may have
    moved or an invoice been paid since. Anything that differs is shown again
    rather than charged, and nothing here has taken money yet."""
    if bf["kind"] == "new_panel":
        return await _revalidate_new_panel(message, state, user_id, bf)
    if bf["kind"] == "topup":
        if black_friday.has_open_bills(user_id):
            await state.clear()
            await _show_items(message, user_id)
            return False
        username = bf["panel_username"]
        if not await owned_panel(user_id, username):
            await state.clear()
            await message.answer(texts.NOT_LINKED_RETRY, reply_markup=await menu_kb_for(user_id))
            return False
        quote = black_friday.Quote(**bf["quote"])
        fresh = black_friday.requote(username, quote)
        if fresh != quote:
            await message.answer(texts.BF_REQUOTED)
            await _show_quote(message, state, username, fresh)
            return False
        return True

    fresh_bf = (
        _debt_bf(user_id, bf["username"]) if bf["kind"] == "debt"
        else _invoice_bf(user_id, bf["invoice_id"])
    )
    if fresh_bf is None:
        await state.clear()
        await message.answer(texts.BF_ITEM_GONE, reply_markup=await menu_kb_for(user_id))
        return False
    if (fresh_bf["original"], fresh_bf["discounted"]) != (bf["original"], bf["discounted"]):
        await message.answer(texts.BF_REQUOTED)
        await _send_item_screen(message, state, fresh_bf)
        return False
    return True


async def _revalidate_new_panel(
    message: Message, state: FSMContext, user_id: int, bf: dict
) -> bool:
    if black_friday.has_open_bills(user_id):
        await state.clear()
        await _show_items(message, user_id)
        return False
    if db.get_pending_panel_request(user_id):
        await state.clear()
        await message.answer(texts.SHOP_ALREADY_PENDING, reply_markup=await menu_kb_for(user_id))
        return False
    if await _username_taken(bf["username"]):
        # Someone took the name while they were deciding: ask for another.
        await state.update_data(bf_new_server=bf["server"])
        await state.set_state(BlackFriday.new_username)
        await message.answer(texts.SHOP_USERNAME_TAKEN, reply_markup=keyboards.cancel_kb())
        return False
    quote = black_friday.Quote(**bf["quote"])
    fresh = black_friday.requote("", quote)
    if fresh != quote:
        await message.answer(texts.BF_REQUOTED)
        await _show_new_quote(message, state, {**bf, "quote": asdict(fresh)})
        return False
    return True


def _amount_of(bf: dict) -> int:
    return bf["quote"]["total"] if bf["kind"] in ("topup", "new_panel") else bf["discounted"]


async def _notify_superadmins(bot: Bot, text: str, reply_markup=None) -> None:
    for superadmin_id in settings.superadmin_id_list:
        try:
            if reply_markup is None:
                await bot.send_message(superadmin_id, text)
            else:
                await bot.send_message(superadmin_id, text, reply_markup=reply_markup)
        except Exception:
            continue


# ---- paying from the wallet ---------------------------------------------------------

@router.callback_query(F.data == "bf_pay:wallet", BlackFriday.awaiting_payment)
async def pay_from_wallet(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    user_id = call.from_user.id
    # A double tap starts two handlers before the first clears the state; the
    # second one is turned away instead of paying twice.
    if user_id in _in_flight_payments:
        await call.answer(texts.PAYMENT_PROCESSING, show_alert=True)
        return
    _in_flight_payments.add(user_id)
    try:
        bf = (await state.get_data()).get("bf")
        if not bf:
            await call.answer(texts.BF_NOT_AVAILABLE, show_alert=True)
            return
        if not black_friday.is_active():
            await call.answer()
            await state.clear()
            await call.message.answer(
                texts.BF_ENDED_PAYMENT, reply_markup=await menu_kb_for(user_id)
            )
            return
        await call.answer()
        if not await _revalidate(call.message, state, user_id, bf):
            return
        if bf["kind"] == "topup":
            await _wallet_topup(call, state, bot, bf)
        elif bf["kind"] == "new_panel":
            await _wallet_new_panel(call, state, bot, bf)
        elif bf["kind"] == "debt":
            await _wallet_debt(call, state, bot, bf)
        else:
            await _wallet_invoice(call, state, bot, bf)
    finally:
        _in_flight_payments.discard(user_id)


async def _wallet_topup(call: CallbackQuery, state: FSMContext, bot: Bot, bf: dict) -> None:
    user_id = call.from_user.id
    username = bf["panel_username"]
    quote = black_friday.Quote(**bf["quote"])

    if db.get_wallet_balance(user_id) < quote.total or not db.spend_wallet(user_id, quote.total):
        await _insufficient_message(call.message, quote.total, user_id)
        return

    try:
        result = await panel_client.topup(user_id, quote.granted_gb, username=username)
    except PanelClientError as exc:
        db.add_wallet_balance(user_id, quote.total)  # refund
        await call.message.answer(
            texts.WEEKLY_TOPUP_FAILED.format(error=exc), reply_markup=await menu_kb_for(user_id)
        )
        return

    await state.clear()
    db.clear_warning_bucket(username)
    db.record_sale(
        telegram_id=user_id, username=username, gb=quote.granted_gb,
        amount=quote.total, method=db.BF_WALLET_METHOD,
    )
    black_friday.record_purchase(
        telegram_id=user_id, username=username, kind=black_friday.PURCHASE_TOPUP,
        paid_gb=quote.paid_gb, gift_gb=quote.gift_gb, amount=quote.total,
        list_amount=quote.list_total, method=black_friday.METHOD_WALLET,
    )
    await call.message.answer(
        texts.BF_WALLET_PAID_SUCCESS.format(
            paid_gb=quote.paid_gb,
            gift_part=texts.BF_GIFT_PART.format(gift_gb=quote.gift_gb) if quote.gift_gb else "",
            added_gb=quote.granted_gb,
            username=username,
            new_gb=bytes_to_gb(result.get("new_traffic_bytes")),
            balance=db.get_wallet_balance(user_id),
        ),
        reply_markup=await menu_kb_for(user_id),
    )
    await _notify_superadmins(
        bot,
        texts.BF_WALLET_NOTIFY_SUPERADMIN.format(
            username=username, telegram_id=user_id, paid_gb=quote.paid_gb,
            gift_gb=quote.gift_gb, total=quote.total,
        ),
    )


async def _create_new_panel_request(
    user_id: int, bf: dict, quote: black_friday.Quote, *, receipt_path: str, method: str
) -> int | None:
    """The panel request for a Black Friday new panel, complete in one INSERT.
    None when the buyer already has an open request."""
    return db.create_panel_request_if_unowned(
        telegram_id=user_id,
        panel_name=bf["server"],
        traffic_gb=quote.granted_gb,
        receipt_path=receipt_path,
        referral_code_id=None,
        desired_username=bf["username"],
        desired_password=bf["password"],
        bf_total=quote.total,
        bf_paid_gb=quote.paid_gb,
        bf_gift_gb=quote.gift_gb,
        bf_list_amount=quote.list_total,
        paid_method=method,
    )


async def _wallet_new_panel(call: CallbackQuery, state: FSMContext, bot: Bot, bf: dict) -> None:
    user_id = call.from_user.id
    quote = black_friday.Quote(**bf["quote"])

    if db.get_wallet_balance(user_id) < quote.total or not db.spend_wallet(user_id, quote.total):
        await _insufficient_message(call.message, quote.total, user_id)
        return

    # The money is taken first; if the request cannot be stored it goes straight
    # back, so nobody pays for a panel nobody will review.
    try:
        request_id = await _create_new_panel_request(
            user_id, bf, quote, receipt_path="", method=black_friday.METHOD_WALLET
        )
    except Exception:
        logger.exception("could not store the black friday panel request for %s", user_id)
        request_id = None
    if request_id is None:
        db.add_wallet_balance(user_id, quote.total)  # refund
        await state.clear()
        pending = db.get_pending_panel_request(user_id)
        await call.message.answer(
            texts.SHOP_ALREADY_PENDING if pending else texts.BF_NEW_REQUEST_FAILED,
            reply_markup=await menu_kb_for(user_id),
        )
        return

    await state.clear()
    await call.message.answer(
        texts.BF_NEW_WALLET_SUBMITTED.format(
            total=quote.total, balance=db.get_wallet_balance(user_id)
        ),
        reply_markup=await menu_kb_for(user_id),
    )
    req = db.get_panel_request(request_id)
    await _notify_superadmins(
        bot,
        black_friday.panel_request_caption(req),
        reply_markup=keyboards.panel_request_approval_kb(request_id),
    )


async def _insufficient_message(message: Message, price: int, user_id: int) -> None:
    await message.answer(
        texts.WALLET_INSUFFICIENT.format(price=price, balance=db.get_wallet_balance(user_id)),
        reply_markup=keyboards.wallet_kb(),
    )


async def _wallet_debt(call: CallbackQuery, state: FSMContext, bot: Bot, bf: dict) -> None:
    user_id = call.from_user.id
    username, original, discounted = bf["username"], bf["original"], bf["discounted"]

    # No partial payments: the full event-rate amount, or nothing is taken.
    if db.get_wallet_balance(user_id) < discounted or not db.spend_wallet(user_id, discounted):
        await _insufficient_message(call.message, discounted, user_id)
        return

    result = black_friday.settle_debt(
        user_id, username, discounted, original, black_friday.METHOD_WALLET
    )
    await state.clear()
    await call.message.answer(
        texts.BF_DEBT_WALLET_SETTLED.format(
            username=html.escape(username), paid=result.applied, cancelled=result.cancelled,
            balance=db.get_wallet_balance(user_id),
        ),
        reply_markup=await menu_kb_for(user_id),
    )
    await _notify_superadmins(
        bot,
        texts.BF_SETTLEMENT_WALLET_NOTIFY_SUPERADMIN.format(
            subject=texts.BF_SUBJECT_DEBT.format(username=html.escape(username)),
            telegram_id=user_id, paid=result.applied, original=result.cancelled,
        ),
    )
    await approvals._maybe_unlock(bot, username, user_id)


async def _wallet_invoice(call: CallbackQuery, state: FSMContext, bot: Bot, bf: dict) -> None:
    user_id = call.from_user.id
    invoice_id, original, discounted = bf["invoice_id"], bf["original"], bf["discounted"]

    if db.get_wallet_balance(user_id) < discounted or not db.spend_wallet(user_id, discounted):
        await _insufficient_message(call.message, discounted, user_id)
        return

    # The atomic pending -> paid flip is what stops this and a card receipt (or
    # the superadmin) both settling the same invoice.
    if not db.mark_invoice_paid(invoice_id):
        db.add_wallet_balance(user_id, discounted)  # refund
        await state.clear()
        await call.message.answer(
            texts.INVOICE_ALREADY_PAID, reply_markup=await menu_kb_for(user_id)
        )
        return

    invoice = db.get_invoice(invoice_id)
    grants_gb = bool(invoice and invoice.admin_username and invoice.traffic_gb > 0)
    if grants_gb:
        try:
            await panel_client.topup(user_id, invoice.traffic_gb, username=invoice.admin_username)
        except PanelClientError as exc:
            # Nothing was credited: put the invoice back and give the money back.
            db.revert_invoice_to_pending(invoice_id)
            db.add_wallet_balance(user_id, discounted)
            await call.message.answer(
                texts.WEEKLY_TOPUP_FAILED.format(error=exc), reply_markup=await menu_kb_for(user_id)
            )
            return

    panel = invoice.admin_username if invoice else None
    db.record_sale(
        telegram_id=user_id, username=panel, gb=invoice.traffic_gb if grants_gb else 0,
        amount=discounted, method="invoice",
    )
    # No ledger discount row here: an invoice's revenue is booked when it is
    # paid, and it was booked above at the event price already. (A weekly debt
    # is different: it was booked at full price on the day of the sale.)
    if original - discounted > 0:
        black_friday.record_purchase(
            telegram_id=user_id, username=panel, kind=black_friday.PURCHASE_INVOICE,
            amount=discounted, list_amount=original, method=black_friday.METHOD_WALLET,
        )

    await state.clear()
    await call.message.answer(
        texts.BF_INVOICE_WALLET_PAID.format(
            id=invoice_id, paid=discounted, balance=db.get_wallet_balance(user_id)
        ),
        reply_markup=await menu_kb_for(user_id),
    )
    await _notify_superadmins(
        bot,
        texts.BF_SETTLEMENT_WALLET_NOTIFY_SUPERADMIN.format(
            subject=texts.BF_SUBJECT_INVOICE.format(id=invoice_id),
            telegram_id=user_id, paid=discounted, original=original,
        ),
    )
    await approvals._maybe_unlock(bot, panel, user_id)


# ---- paying by card -------------------------------------------------------------------

@router.callback_query(F.data == "bf_pay:card", BlackFriday.awaiting_payment)
async def show_card_payment(call: CallbackQuery, state: FSMContext) -> None:
    user_id = call.from_user.id
    bf = (await state.get_data()).get("bf")
    if not bf:
        await call.answer(texts.BF_NOT_AVAILABLE, show_alert=True)
        return
    if not black_friday.is_active():
        await call.answer()
        await state.clear()
        await call.message.answer(texts.BF_ENDED_PAYMENT, reply_markup=await menu_kb_for(user_id))
        return
    await call.answer()
    if not await _revalidate(call.message, state, user_id, bf):
        return

    card_number = db.get_setting("card_number")
    if not card_number:
        await call.message.answer(texts.CARD_NOT_CONFIGURED)
        return

    await state.set_state(BlackFriday.receipt)
    await call.message.answer(
        texts.BF_CARD_INSTRUCTIONS.format(price=_amount_of(bf), card_number=card_number),
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(BlackFriday.receipt, ~F.text.in_(ALL_MENU_TEXTS))
async def get_receipt(message: Message, state: FSMContext, bot: Bot) -> None:
    if not message.photo:
        await message.answer(texts.NOT_A_PHOTO)
        return

    data = await state.get_data()
    await state.clear()
    user_id = message.from_user.id
    bf = data.get("bf")
    if not bf:
        await message.answer(texts.BF_NOT_AVAILABLE, reply_markup=await menu_kb_for(user_id))
        return

    # Checked again here, not only when the menu opened: this is the last point
    # before a request lands in front of the superadmin. (The event itself is
    # not re-checked: the price was shown while it ran and the card payment was
    # started then, so the receipt is honoured.)
    if bf["kind"] == "new_panel":
        if black_friday.has_open_bills(user_id):
            await message.answer(texts.BF_RECEIPT_BLOCKED, reply_markup=await menu_kb_for(user_id))
            return
    elif bf["kind"] == "topup":
        if black_friday.has_open_bills(user_id):
            await message.answer(texts.BF_RECEIPT_BLOCKED, reply_markup=await menu_kb_for(user_id))
            return
        if not await owned_panel(user_id, bf["panel_username"]):
            await message.answer(texts.NOT_LINKED_RETRY, reply_markup=await menu_kb_for(user_id))
            return
    elif bf["kind"] == "debt":
        record = db.get_debt_record(bf["username"])
        if not record or record["amount"] <= 0 or record["telegram_id"] != user_id:
            await message.answer(texts.BF_ITEM_RECEIPT_GONE, reply_markup=await menu_kb_for(user_id))
            return
    else:
        invoice = db.get_invoice(bf["invoice_id"])
        if invoice is None or invoice.telegram_id != user_id or invoice.status != "pending":
            await message.answer(texts.BF_ITEM_RECEIPT_GONE, reply_markup=await menu_kb_for(user_id))
            return

    os.makedirs(settings.media_dir, exist_ok=True)
    receipt_path = os.path.join(settings.media_dir, f"receipt_{uuid.uuid4().hex}.jpg")
    await bot.download(message.photo[-1], destination=receipt_path)

    if bf["kind"] == "new_panel":
        await _card_new_panel(message, bot, bf, receipt_path)
        return
    if bf["kind"] == "topup":
        quote = black_friday.Quote(**bf["quote"])
        request_id = db.create_request(
            admin_telegram_id=user_id,
            admin_username=bf["panel_username"],
            requested_gb=quote.granted_gb,
            toman_amount=quote.total,
            receipt_path=receipt_path,
            kind=black_friday.KIND_TOPUP,
            bf_paid_gb=quote.paid_gb,
            bf_gift_gb=quote.gift_gb,
            bf_credit_amount=quote.list_total,
        )
    elif bf["kind"] == "debt":
        request_id = db.create_request(
            admin_telegram_id=user_id,
            admin_username=bf["username"],
            requested_gb=0,
            toman_amount=bf["discounted"],
            receipt_path=receipt_path,
            kind=black_friday.KIND_SETTLEMENT,
            bf_credit_amount=bf["original"],
        )
    else:
        # The same request as paying an invoice normally: the existing approval
        # marks it paid and grants its traffic. Only the amount differs, and the
        # original in bf_credit_amount tells approval to write the discount down.
        request_id = db.create_request(
            admin_telegram_id=user_id,
            admin_username=None,
            requested_gb=0,
            toman_amount=bf["discounted"],
            receipt_path=receipt_path,
            kind="invoice",
            invoice_id=bf["invoice_id"],
            bf_credit_amount=bf["original"],
        )

    await message.answer(
        texts.REQUEST_SUBMITTED + texts.RECEIPT_WARNING, reply_markup=await menu_kb_for(user_id)
    )
    req = db.get_request(request_id)
    await notify.send_receipt_to_superadmins(
        bot,
        photo=FSInputFile(receipt_path),
        caption=black_friday.request_caption(req) + auto_approve.caption_note(),
        reply_markup=keyboards.approval_kb(request_id, user_id),
        request_id=request_id,
        kind=req.kind,
    )


async def _card_new_panel(message: Message, bot: Bot, bf: dict, receipt_path: str) -> None:
    user_id = message.from_user.id
    quote = black_friday.Quote(**bf["quote"])
    request_id = await _create_new_panel_request(
        user_id, bf, quote, receipt_path=receipt_path, method=black_friday.METHOD_CARD
    )
    if request_id is None:
        await message.answer(texts.SHOP_ALREADY_PENDING, reply_markup=await menu_kb_for(user_id))
        return
    await message.answer(
        texts.SHOP_REQUEST_SUBMITTED + texts.SHOP_RECEIPT_WARNING,
        reply_markup=await menu_kb_for(user_id),
    )
    req = db.get_panel_request(request_id)
    await notify.send_receipt_to_superadmins(
        bot,
        photo=FSInputFile(receipt_path),
        caption=black_friday.panel_request_caption(req),
        reply_markup=keyboards.panel_request_approval_kb(request_id),
        request_id=request_id,
        kind="panel",
    )


# ---- stale buttons ----------------------------------------------------------------------

@router.callback_query(
    F.data.startswith("bf_pay:") | F.data.startswith("bf_pkg:")
    | F.data.startswith("bf_target:") | F.data.startswith("bf_srv:")
)
async def stale_button(call: CallbackQuery) -> None:
    """A Black Friday button whose flow is gone (restart, cancel, a newer
    screen): say so instead of leaving the tap unanswered."""
    await call.answer(texts.BF_NOT_AVAILABLE, show_alert=True)


# ---- superadmin stats ---------------------------------------------------------------------

@router.message(F.text == texts.BTN_BF_STATS, SuperadminFilter())
async def show_stats(message: Message) -> None:
    await message.answer(
        black_friday.stats_text(), reply_markup=superadmin_kb(message.from_user.id)
    )
