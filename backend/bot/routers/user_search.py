"""Superadmin: look a customer up and act on them in one place.

Shows everything the bot knows about a person — panels, wallet, debts, open
invoices, recent transactions — with buttons to deduct from their wallet, issue
an invoice, or remove one.
"""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import keyboards, texts
from backend.bot.filters import SuperadminFilter
from backend.bot.invoices import describe_due, due_at_for
from backend.bot.nav import ALL_MENU_TEXTS, superadmin_kb
from backend.bot.states import DeductWallet, NewInvoice, SearchUser
from backend.bot import db
from backend.bot.panel_client import PanelClientError as NexraPanelError
from backend.bot import panel_client as nexra_panel
from backend.bot.units import bytes_to_gb

router = Router(name="user_search")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())


async def _resolve(query: str) -> tuple[int | None, list[dict]]:
    """Find a person by numeric id, Telegram @username, or panel username.

    Returns (telegram_id, their panels).
    """
    query = query.strip().lstrip("@")

    try:
        all_admins = await nexra_panel.list_all_admins()
    except NexraPanelError:
        all_admins = []

    telegram_id: int | None = None
    if query.lstrip("-").isdigit():
        telegram_id = int(query)
    else:
        # Panel username first — it's the identifier the superadmin sees most.
        match = next((a for a in all_admins if a.get("username") == query), None)
        if match and match.get("telegram_id"):
            telegram_id = match["telegram_id"]
        else:
            for user in db.list_known_users():
                record = db.get_user(user)
                if record and (record.get("username") or "").lower() == query.lower():
                    telegram_id = user
                    break

    if telegram_id is None:
        return None, []
    return telegram_id, [a for a in all_admins if a.get("telegram_id") == telegram_id]


def _render_profile(telegram_id: int, panels: list[dict]) -> str:
    record = db.get_user(telegram_id)
    name = (record or {}).get("full_name") or "—"
    mention = f"@{record['username']}" if record and record.get("username") else "—"

    text = texts.USER_PROFILE.format(
        name=name,
        telegram_id=telegram_id,
        mention=mention,
        wallet=db.get_wallet_balance(telegram_id),
    )

    if panels:
        lines = "".join(
            texts.USER_PROFILE_PANEL_LINE.format(
                username=p["username"],
                remaining_gb=bytes_to_gb(p.get("traffic")),
                initial_gb=bytes_to_gb(p.get("initial_traffic")),
            )
            for p in panels
        )
        text += texts.USER_PROFILE_PANELS.format(panels=lines)
    else:
        text += texts.USER_PROFILE_NO_PANELS

    debts = [d for d in db.list_outstanding_debts() if d["telegram_id"] == telegram_id]
    if debts:
        text += texts.USER_PROFILE_DEBTS.format(
            debts="".join(
                texts.USER_PROFILE_DEBT_LINE.format(username=d["username"], amount=d["amount"])
                for d in debts
            )
        )
    else:
        text += texts.USER_PROFILE_NO_DEBTS

    invoices = db.list_pending_invoices(telegram_id)
    if invoices:
        text += texts.USER_PROFILE_INVOICES.format(
            invoices="".join(
                texts.USER_PROFILE_INVOICE_LINE.format(
                    id=i.id, amount=i.amount, description=i.description or "—"
                )
                for i in invoices
            )
        )
    else:
        text += texts.USER_PROFILE_NO_INVOICES

    history = db.list_requests_for(telegram_id, limit=8)
    if history:
        text += texts.USER_PROFILE_HISTORY.format(
            history="".join(
                texts.USER_PROFILE_HISTORY_LINE.format(
                    kind=texts.KIND_LABELS.get(r.kind, r.kind),
                    amount=r.toman_amount,
                    status=texts.STATUS_LABELS.get(r.status, r.status),
                    date=r.created_at[:10],
                )
                for r in history
            )
        )
    else:
        text += texts.USER_PROFILE_NO_HISTORY

    return text


@router.message(F.text == texts.BTN_SEARCH_USER)
async def start_search(message: Message, state: FSMContext) -> None:
    await state.set_state(SearchUser.query)
    await message.answer(texts.ASK_SEARCH_QUERY, reply_markup=keyboards.cancel_kb())


@router.message(SearchUser.query, ~F.text.in_(ALL_MENU_TEXTS))
async def do_search(message: Message, state: FSMContext) -> None:
    await state.clear()
    telegram_id, panels = await _resolve(message.text or "")
    if telegram_id is None:
        await message.answer(texts.USER_NOT_FOUND, reply_markup=superadmin_kb(message.from_user.id))
        return

    await message.answer(
        _render_profile(telegram_id, panels),
        reply_markup=keyboards.user_actions_kb(telegram_id),
    )


@router.callback_query(F.data.startswith("usr_deduct:"))
async def start_deduct(call: CallbackQuery, state: FSMContext) -> None:
    target = int(call.data.split(":", 1)[1])
    await state.set_state(DeductWallet.amount)
    await state.update_data(deduct_target=target)
    await call.answer()
    await call.message.answer(texts.ASK_DEDUCT_AMOUNT, reply_markup=keyboards.cancel_kb())


@router.message(DeductWallet.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_deduct(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", "").replace("٬", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return

    data = await state.get_data()
    await state.clear()
    target, amount = data["deduct_target"], int(raw)
    balance = db.deduct_wallet(target, amount)

    await message.answer(
        texts.DEDUCT_SUCCESS.format(amount=amount, balance=balance),
        reply_markup=superadmin_kb(message.from_user.id),
    )
    try:
        await bot.send_message(target, texts.WALLET_BALANCE.format(balance=balance))
    except Exception:
        pass


@router.callback_query(F.data.startswith("usr_invoice:"))
async def invoice_for_user(call: CallbackQuery, state: FSMContext) -> None:
    """Jump straight into the invoice flow with the target already filled in."""
    target = int(call.data.split(":", 1)[1])
    await state.set_state(NewInvoice.amount)
    await state.update_data(invoice_target=target)
    await call.answer()
    await call.message.answer(texts.ASK_INVOICE_AMOUNT, reply_markup=keyboards.cancel_kb())


@router.callback_query(F.data.startswith("usr_delinv:"))
async def choose_invoice_to_delete(call: CallbackQuery) -> None:
    target = int(call.data.split(":", 1)[1])
    invoices = db.list_pending_invoices(target)
    if not invoices:
        await call.answer(texts.NO_INVOICES, show_alert=True)
        return
    await call.answer()
    await call.message.answer(
        texts.CHOOSE_INVOICE_TO_DELETE, reply_markup=keyboards.invoice_delete_kb(invoices)
    )


@router.callback_query(F.data.startswith("delinv:"))
async def delete_invoice(call: CallbackQuery) -> None:
    invoice_id = int(call.data.split(":", 1)[1])
    if db.cancel_invoice(invoice_id):
        await call.answer(texts.INVOICE_DELETED.format(id=invoice_id))
        await call.message.edit_reply_markup(reply_markup=None)
        await call.message.answer(texts.INVOICE_DELETED.format(id=invoice_id))
    else:
        await call.answer(texts.INVOICE_DELETE_FAILED, show_alert=True)
