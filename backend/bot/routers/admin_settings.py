"""Superadmin-facing: configure the per-GB price, the card-to-card number, the
force-join channel, admin creation, panel creation, and per-admin pricing."""

from __future__ import annotations

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import auto_approve, bills, keyboards, texts
from backend.bot.filters import SuperadminFilter
from backend.bot.invoices import describe_due, due_at_for
from backend.bot.nav import ALL_MENU_TEXTS, menu_kb_for, remember_section, superadmin_kb
from backend.bot.states import (
    Broadcast,
    ClearAdminPrice,
    CreateAdmin,
    CreatePanel,
    DeleteAdmin,
    GrantTraffic,
    GrantWallet,
    NewInvoice,
    ReferralManage,
    SetAdminPrice,
    SetCardNumber,
    SetForceJoinChannel,
    SetPricePerGb,
    TogglePaymentMode,
)
from backend.bot import db
from backend.bot.billing import apply_wallet_to_debts
from backend.bot.config import bot_config as settings
from backend.bot.panel_client import PanelClientError
from backend.bot import panel_client
from backend.bot.units import bytes_to_gb
from backend.db.engin import sessionLocal
from backend.db import crud

router = Router(name="admin_settings")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())


_SECTIONS = {
    texts.BTN_SEC_PANELS: (texts.SECTION_PANELS, "panels"),
    texts.BTN_SEC_FINANCE: (texts.SECTION_FINANCE, "finance"),
    texts.BTN_SEC_USERS: (texts.SECTION_USERS, "users"),
    texts.BTN_SEC_SETTINGS: (texts.SECTION_SETTINGS, "settings"),
    texts.BTN_TUTORIALS: (texts.SECTION_TUTORIALS, "tutorials"),
}


@router.message(F.text.in_(_SECTIONS))
async def open_section(message: Message, state: FSMContext) -> None:
    # Leaving a half-finished flow by tapping a section is a deliberate exit, so
    # drop the state rather than letting the next answer land in it.
    await state.clear()
    prompt, section = _SECTIONS[message.text]
    remember_section(message.from_user.id, section)
    await message.answer(prompt, reply_markup=superadmin_kb(message.from_user.id))


@router.message(F.text == texts.BTN_SET_PRICE)
async def start_set_price(message: Message, state: FSMContext) -> None:
    await state.set_state(SetPricePerGb.value)
    await message.answer(texts.ASK_PRICE_PER_GB, reply_markup=keyboards.cancel_kb())


@router.message(SetPricePerGb.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_price(message: Message, state: FSMContext) -> None:
    await state.clear()
    raw = (message.text or "").strip().replace(",", "")
    try:
        price = float(raw)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_PRICE, reply_markup=superadmin_kb(message.from_user.id))
        return
    db.set_setting("price_per_gb", str(price))
    await message.answer(
        texts.PRICE_SET_CONFIRM.format(price=int(price)), reply_markup=superadmin_kb(message.from_user.id)
    )


@router.message(F.text == texts.BTN_SET_CARD)
async def start_set_card(message: Message, state: FSMContext) -> None:
    await state.set_state(SetCardNumber.value)
    await message.answer(texts.ASK_CARD_NUMBER, reply_markup=keyboards.cancel_kb())


@router.message(SetCardNumber.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_card(message: Message, state: FSMContext) -> None:
    await state.clear()
    card_number = (message.text or "").strip()
    if not card_number:
        await message.answer(texts.INVALID_CARD_NUMBER, reply_markup=superadmin_kb(message.from_user.id))
        return
    db.set_setting("card_number", card_number)
    await message.answer(texts.CARD_SET_CONFIRM, reply_markup=superadmin_kb(message.from_user.id))


@router.message(F.text == texts.BTN_SET_FORCE_JOIN_CHANNEL)
async def start_set_channel(message: Message, state: FSMContext) -> None:
    await state.set_state(SetForceJoinChannel.value)
    await message.answer(texts.ASK_FORCE_JOIN_CHANNEL, reply_markup=keyboards.cancel_kb())


async def _report_channel_access(message: Message, bot: Bot, channel: str) -> None:
    """Say whether the gate can actually work.

    The middleware deliberately fails open when it can't read the channel, so a
    bot that isn't an admin there lets everyone straight through — silently. The
    superadmin needs to hear about that at the moment they configure it, not
    discover it from users who never got asked to join.
    """
    try:
        await bot.get_chat_member(channel, bot.id)
    except Exception as exc:
        await message.answer(
            texts.FORCE_JOIN_BOT_NOT_ADMIN.format(channel=channel, error=exc),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return
    await message.answer(texts.FORCE_JOIN_CHECK_OK.format(channel=channel))


@router.message(SetForceJoinChannel.value, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_channel(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    channel = (message.text or "").strip()
    if not channel.startswith("@"):
        await message.answer(texts.INVALID_CHANNEL, reply_markup=superadmin_kb(message.from_user.id))
        return
    db.set_setting("force_join_channel", channel)
    await message.answer(
        texts.FORCE_JOIN_CHANNEL_SET.format(channel=channel),
        reply_markup=superadmin_kb(message.from_user.id),
    )
    await _report_channel_access(message, bot, channel)


@router.message(F.text == texts.BTN_TOGGLE_FORCE_JOIN)
async def toggle_force_join(message: Message, bot: Bot) -> None:
    channel = db.get_setting("force_join_channel")
    currently_on = db.get_setting("force_join_enabled") == "1"
    if not currently_on and not channel:
        await message.answer(texts.FORCE_JOIN_NO_CHANNEL_YET)
        return
    db.set_setting("force_join_enabled", "0" if currently_on else "1")
    await message.answer(
        texts.FORCE_JOIN_ENABLED_OFF if currently_on else texts.FORCE_JOIN_ENABLED_ON
    )
    if not currently_on:
        await _report_channel_access(message, bot, channel)


@router.message(F.text == texts.BTN_ALL_PANELS)
async def list_all_panels(message: Message) -> None:
    try:
        admins = await panel_client.list_all_admins()
    except PanelClientError as exc:
        await message.answer(texts.SYNC_FAILED.format(error=exc))
        return
    if not admins:
        await message.answer(texts.NO_PANELS)
        return

    header = texts.ALL_PANELS_HEADER.format(count=len(admins))
    chunks: list[str] = []
    current = header
    for a in admins:
        line = texts.ADMIN_PANEL_LINE.format(
            username=a["username"],
            status="" if a.get("is_active") else texts.PANEL_INACTIVE_MARK,
            remaining_gb=bytes_to_gb(a.get("traffic")),
            initial_gb=bytes_to_gb(a.get("initial_traffic")),
            telegram_id=a.get("telegram_id") or "—",
        )
        if len(current) + len(line) > 3500:
            chunks.append(current)
            current = ""
        current += line
    chunks.append(current)

    for chunk in chunks:
        await message.answer(chunk)


@router.message(F.text == texts.BTN_GRANT_TRAFFIC)
async def start_grant(message: Message, state: FSMContext) -> None:
    await state.set_state(GrantTraffic.username)
    await message.answer(texts.ASK_GRANT_USERNAME, reply_markup=keyboards.cancel_kb())


@router.message(GrantTraffic.username, ~F.text.in_(ALL_MENU_TEXTS))
async def get_grant_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.ASK_GRANT_USERNAME, reply_markup=keyboards.cancel_kb())
        return
    await state.update_data(grant_username=username)
    await state.set_state(GrantTraffic.amount)
    await message.answer(
        texts.ASK_GRANT_AMOUNT.format(username=username), reply_markup=keyboards.cancel_kb()
    )


@router.message(GrantTraffic.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_grant(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", ".")
    try:
        amount = float(raw)
        if amount <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_AMOUNT_GB)
        return

    data = await state.get_data()
    await state.clear()
    username = data["grant_username"]

    try:
        result = await panel_client.grant(username, amount)
    except PanelClientError as exc:
        await message.answer(
            texts.GRANT_FAILED.format(error=exc), reply_markup=superadmin_kb(message.from_user.id)
        )
        return

    new_gb = bytes_to_gb(result.get("new_traffic_bytes"))
    db.clear_warning_bucket(username)
    await message.answer(
        texts.GRANT_SUCCESS.format(added_gb=amount, username=username, new_gb=new_gb),
        reply_markup=superadmin_kb(message.from_user.id),
    )

    target_telegram_id = result.get("telegram_id")
    if target_telegram_id:
        try:
            await bot.send_message(
                target_telegram_id,
                texts.GRANT_NOTIFY_ADMIN.format(
                    username=username, added_gb=amount, new_gb=new_gb
                ),
            )
        except Exception:
            pass


@router.message(F.text == texts.BTN_NEW_INVOICE)
async def start_invoice(message: Message, state: FSMContext) -> None:
    await state.set_state(NewInvoice.target)
    await message.answer(texts.ASK_INVOICE_TARGET, reply_markup=keyboards.cancel_kb())


@router.message(NewInvoice.target, ~F.text.in_(ALL_MENU_TEXTS))
async def invoice_target(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(texts.ASK_INVOICE_TARGET)
        return
    await state.update_data(invoice_target=int(raw))
    await state.set_state(NewInvoice.amount)
    await message.answer(texts.ASK_INVOICE_AMOUNT, reply_markup=keyboards.cancel_kb())


@router.message(NewInvoice.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def invoice_amount(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", "").replace("٬", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return
    await state.update_data(invoice_amount=int(raw))
    await state.set_state(NewInvoice.description)
    await message.answer(texts.ASK_INVOICE_DESCRIPTION, reply_markup=keyboards.cancel_kb())


@router.message(NewInvoice.description, ~F.text.in_(ALL_MENU_TEXTS))
async def invoice_description(message: Message, state: FSMContext) -> None:
    description = (message.text or "").strip()
    if not description:
        await message.answer(texts.ASK_INVOICE_DESCRIPTION)
        return
    await state.update_data(invoice_description=description)
    await state.set_state(NewInvoice.due)
    await message.answer(texts.ASK_INVOICE_DUE, reply_markup=keyboards.invoice_due_kb())


@router.callback_query(F.data.startswith("invoice_due:"), NewInvoice.due)
async def invoice_due(call: CallbackQuery, state: FSMContext, bot: Bot) -> None:
    key = call.data.split(":", 1)[1]
    data = await state.get_data()
    await state.clear()
    await call.answer()

    due_at = due_at_for(key)
    target_id = data["invoice_target"]
    # Checked before the invoice exists — afterwards everyone is a customer.
    was_customer = db.has_billing_account(target_id)
    invoice_id = db.create_invoice(
        telegram_id=target_id,
        amount=data["invoice_amount"],
        description=data["invoice_description"],
        due_at=due_at,
    )

    delivered = True
    try:
        await bot.send_message(
            target_id,
            texts.INVOICE_FOR_CUSTOMER.format(
                id=invoice_id,
                amount=data["invoice_amount"],
                description=data["invoice_description"],
                due=describe_due(due_at),
            ),
            reply_markup=keyboards.pay_invoice_kb(invoice_id),
        )
    except Exception:
        delivered = False

    await call.message.answer(
        texts.INVOICE_CREATED.format(
            id=invoice_id,
            telegram_id=target_id,
            amount=data["invoice_amount"],
            due=describe_due(due_at),
        ),
        reply_markup=superadmin_kb(call.from_user.id),
    )
    if not delivered:
        await call.message.answer(texts.INVOICE_CREATE_NOT_DELIVERED)
    elif not was_customer:
        # A first bill is what opens the wallet and invoices to them, and a reply
        # keyboard only changes when a message arrives carrying the new one.
        try:
            await bot.send_message(
                target_id, texts.ACCOUNT_ACTIVATED, reply_markup=await menu_kb_for(target_id)
            )
        except Exception:
            pass


@router.message(F.text.in_({texts.BTN_INVOICES, texts.BTN_DEBTS}))
async def list_invoices(message: Message) -> None:
    """Everything owed — invoices and weekly credit alike — grouped by customer,
    most urgent first, each with its own warning buttons.

    BTN_DEBTS is only matched so a keyboard still showing the old separate debts
    button lands somewhere sensible.
    """
    customers = bills.by_customer(bills.open_bills())
    if not customers:
        await message.answer(texts.NO_INVOICES)
        return
    await message.answer(bills.render_summary(customers))
    for customer in customers:
        await message.answer(
            bills.render_customer(customer), reply_markup=keyboards.bill_actions_kb(customer)
        )


@router.callback_query(F.data.startswith("warn:"))
async def send_nonpayment_warning(call: CallbackQuery, bot: Bot) -> None:
    bill = bills.find(call.data.split(":", 1)[1])
    if bill is None or bill.telegram_id is None:
        await call.answer(texts.WARNING_BILL_GONE, show_alert=True)
        return
    try:
        await bot.send_message(
            bill.telegram_id, bills.render_warning(bill), reply_markup=keyboards.bill_pay_kb(bill)
        )
    except Exception:
        await call.answer(texts.WARNING_NOT_DELIVERED, show_alert=True)
        return

    bills.mark_warned(bill)
    await call.answer(texts.WARNING_SENT_TOAST)
    # Redraw this customer's card so its "last warned" line shows what was just sent.
    refreshed = bills.by_customer(bills.open_bills(bill.telegram_id))
    if refreshed:
        try:
            await call.message.edit_text(
                bills.render_customer(refreshed[0]),
                reply_markup=keyboards.bill_actions_kb(refreshed[0]),
            )
        except Exception:
            pass


@router.message(F.text == texts.BTN_TOGGLE_AUTO_APPROVE)
async def toggle_auto_approve(message: Message) -> None:
    turning_on = not auto_approve.is_enabled()
    auto_approve.set_enabled(turning_on)
    await message.answer(
        texts.AUTO_APPROVE_ON if turning_on else texts.AUTO_APPROVE_OFF,
        reply_markup=superadmin_kb(message.from_user.id),
    )


@router.message(F.text == texts.BTN_CREATE_ADMIN)
async def start_create_admin(message: Message, state: FSMContext) -> None:
    await state.set_state(CreateAdmin.username)
    await message.answer(texts.ASK_NEW_ADMIN_USERNAME, reply_markup=keyboards.cancel_kb())


@router.message(CreateAdmin.username, ~F.text.in_(ALL_MENU_TEXTS))
async def create_admin_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip().lower()
    if not username:
        await message.answer(texts.ASK_NEW_ADMIN_USERNAME)
        return
    # Check if username is already taken (MIT Panel DB + all Marzban panels)
    try:
        taken = await panel_client.check_username_taken(username)
    except Exception:
        taken = False
    if taken:
        await message.answer(texts.SHOP_USERNAME_TAKEN)
        return
    await state.update_data(new_username=username)
    await state.set_state(CreateAdmin.password)
    await message.answer(texts.ASK_NEW_ADMIN_PASSWORD, reply_markup=keyboards.cancel_kb())


@router.message(CreateAdmin.password, ~F.text.in_(ALL_MENU_TEXTS))
async def create_admin_password(message: Message, state: FSMContext) -> None:
    password = (message.text or "").strip()
    if not password:
        await message.answer(texts.INVALID_PASSWORD)
        return
    if len(password) < 8 or not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        await message.answer(texts.SHOP_PASSWORD_WEAK)
        return
    await state.update_data(new_password=password)

    try:
        panels = await panel_client.list_panels()
    except PanelClientError as exc:
        await state.clear()
        await message.answer(
            texts.CREATE_ADMIN_FAILED.format(error=exc),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return

    if not panels:
        await state.clear()
        await message.answer(texts.NO_MARZBAN_PANELS, reply_markup=superadmin_kb(message.from_user.id))
        return

    # A single panel needs no choosing; skip straight to the next question.
    if len(panels) == 1:
        await state.update_data(new_panel=panels[0])
        await state.set_state(CreateAdmin.traffic)
        await message.answer(texts.ASK_NEW_ADMIN_TRAFFIC, reply_markup=keyboards.cancel_kb())
        return

    await state.update_data(panel_choices=panels)
    await state.set_state(CreateAdmin.panel)
    await message.answer(
        texts.ASK_NEW_ADMIN_PANEL, reply_markup=keyboards.panel_name_picker_kb(panels)
    )


@router.callback_query(F.data.startswith("newadmin_panel:"), CreateAdmin.panel)
async def create_admin_panel(call: CallbackQuery, state: FSMContext) -> None:
    data = await state.get_data()
    choices = data.get("panel_choices") or []
    index = int(call.data.split(":", 1)[1])
    # A keyboard left over from an earlier, abandoned run would point at a list
    # this state no longer has.
    if index >= len(choices):
        await call.answer(texts.PANEL_CHOICE_EXPIRED, show_alert=True)
        return

    await state.update_data(new_panel=choices[index])
    await state.set_state(CreateAdmin.traffic)
    await call.answer()
    await call.message.answer(texts.ASK_NEW_ADMIN_TRAFFIC, reply_markup=keyboards.cancel_kb())


@router.message(CreateAdmin.panel, ~F.text.in_(ALL_MENU_TEXTS))
async def create_admin_panel_typed(message: Message, state: FSMContext) -> None:
    """Typing instead of tapping would otherwise go unanswered."""
    data = await state.get_data()
    await message.answer(
        texts.ASK_NEW_ADMIN_PANEL,
        reply_markup=keyboards.panel_name_picker_kb(data.get("panel_choices") or []),
    )


@router.message(CreateAdmin.traffic, ~F.text.in_(ALL_MENU_TEXTS))
async def create_admin_traffic(message: Message, state: FSMContext) -> None:
    try:
        traffic = float((message.text or "").strip().replace(",", "."))
        if traffic < 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_AMOUNT_GB)
        return
    await state.update_data(new_traffic=traffic)
    await state.set_state(CreateAdmin.expiry)
    await message.answer(texts.ASK_NEW_ADMIN_EXPIRY, reply_markup=keyboards.cancel_kb())


@router.message(CreateAdmin.expiry, ~F.text.in_(ALL_MENU_TEXTS))
async def create_admin_expiry(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        expiry = None
    elif raw.isdigit() and int(raw) > 0:
        expiry = int(raw)
    else:
        await message.answer(texts.ASK_NEW_ADMIN_EXPIRY)
        return
    await state.update_data(new_expiry=expiry)
    await state.set_state(CreateAdmin.telegram_id)
    await message.answer(texts.ASK_NEW_ADMIN_TELEGRAM, reply_markup=keyboards.cancel_kb())


@router.message(CreateAdmin.telegram_id, ~F.text.in_(ALL_MENU_TEXTS))
async def create_admin_finish(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip()
    if raw == "-":
        target_id = None
    elif raw.lstrip("-").isdigit():
        target_id = int(raw)
    else:
        await message.answer(texts.ASK_NEW_ADMIN_TELEGRAM)
        return

    data = await state.get_data()
    await state.clear()
    await message.answer(texts.CREATING_ADMIN)

    try:
        result = await panel_client.create_admin(
            username=data["new_username"],
            password=data["new_password"],
            panel=data["new_panel"],
            traffic_gb=data["new_traffic"],
            expiry_days=data["new_expiry"],
            telegram_id=target_id,
        )
    except PanelClientError as exc:
        await message.answer(
            texts.CREATE_ADMIN_FAILED.format(error=exc),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return

    expiry = result.get("expiry_date")
    panel_url = settings.panel_link_url
    success_text = texts.CREATE_ADMIN_SUCCESS.format(
        url=panel_url,
        username=data["new_username"],
        password=data["new_password"],
        traffic_gb=data["new_traffic"],
        expiry=expiry[:10] if expiry else "بدون انقضا",
    )
    await message.answer(
        success_text,
        reply_markup=superadmin_kb(message.from_user.id),
    )

    if target_id:
        db.ensure_user(target_id)
        db.set_user_linked(target_id, True)
        try:
            await bot.send_message(target_id, success_text)
        except Exception:
            pass


@router.message(F.text == texts.BTN_TOGGLE_DELAYED)
async def start_toggle_delayed(message: Message, state: FSMContext) -> None:
    await state.update_data(payment_mode="delayed")
    await state.set_state(TogglePaymentMode.username)
    enabled = db.list_delayed_enabled()
    current = ("\n\nفعال‌ها: " + "، ".join(enabled)) if enabled else ""
    await message.answer(texts.ASK_PAYMENT_MODE_USERNAME + current, reply_markup=keyboards.cancel_kb())


@router.message(F.text == texts.BTN_TOGGLE_CONSUMPTION)
async def start_toggle_consumption(message: Message, state: FSMContext) -> None:
    await state.update_data(payment_mode="consumption")
    await state.set_state(TogglePaymentMode.username)
    enabled = db.list_consumption_enabled()
    current = ("\n\nفعال‌ها: " + "، ".join(enabled)) if enabled else ""
    await message.answer(texts.ASK_PAYMENT_MODE_USERNAME + current, reply_markup=keyboards.cancel_kb())


@router.message(TogglePaymentMode.username, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_toggle_payment_mode(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    await state.clear()
    username = (message.text or "").strip()
    mode = data.get("payment_mode", "delayed")
    if not username:
        await message.answer(texts.ASK_PAYMENT_MODE_USERNAME, reply_markup=superadmin_kb(message.from_user.id))
        return

    current_mode = db.get_weekly_mode(username)

    if current_mode == mode:
        # Already in this mode -> disable
        db.set_weekly_enabled(username, False)
        if mode == "delayed":
            template = texts.DELAYED_ENABLED_OFF
        else:
            template = texts.CONSUMPTION_ENABLED_OFF
    else:
        # Enable this mode (switches from disabled or from the other mode)
        db.set_weekly_mode(username, mode)
        if mode == "delayed":
            template = texts.DELAYED_ENABLED_ON
        else:
            template = texts.CONSUMPTION_ENABLED_ON

    await message.answer(
        template.format(username=username), reply_markup=superadmin_kb(message.from_user.id)
    )


@router.message(F.text == texts.BTN_GRANT_WALLET)
async def start_grant_wallet(message: Message, state: FSMContext) -> None:
    await state.set_state(GrantWallet.telegram_id)
    await message.answer(texts.ASK_GRANT_WALLET_ID, reply_markup=keyboards.cancel_kb())


@router.message(GrantWallet.telegram_id, ~F.text.in_(ALL_MENU_TEXTS))
async def get_grant_wallet_id(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return
    await state.update_data(target_telegram_id=int(raw))
    await state.set_state(GrantWallet.amount)
    await message.answer(texts.ASK_GRANT_WALLET_AMOUNT, reply_markup=keyboards.cancel_kb())


@router.message(GrantWallet.amount, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_grant_wallet(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", "")
    if not raw.isdigit() or int(raw) <= 0:
        await message.answer(texts.INVALID_WALLET_AMOUNT)
        return

    data = await state.get_data()
    await state.clear()
    target_id, amount = data["target_telegram_id"], int(raw)

    db.add_wallet_balance(target_id, amount)
    apply_wallet_to_debts(target_id)
    balance = db.get_wallet_balance(target_id)

    await message.answer(
        texts.GRANT_WALLET_SUCCESS.format(telegram_id=target_id, balance=balance),
        reply_markup=superadmin_kb(message.from_user.id),
    )
    try:
        await bot.send_message(
            target_id, texts.WALLET_CHARGED_ADMIN.format(amount=amount, balance=balance)
        )
    except Exception:
        pass


@router.message(F.text == texts.BTN_BROADCAST)
async def start_broadcast(message: Message, state: FSMContext) -> None:
    await state.set_state(Broadcast.text)
    await message.answer(texts.ASK_BROADCAST_TEXT, reply_markup=keyboards.cancel_kb())


@router.message(Broadcast.text, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_broadcast(message: Message, state: FSMContext, bot: Bot) -> None:
    await state.clear()
    body = message.text or ""
    if not body.strip():
        await message.answer(texts.INVALID_PASSWORD, reply_markup=superadmin_kb(message.from_user.id))
        return

    sent = failed = 0
    for telegram_id in db.list_known_users():
        try:
            await bot.send_message(telegram_id, texts.BROADCAST_PREFIX + body)
            sent += 1
        except Exception:
            failed += 1

    await message.answer(
        texts.BROADCAST_RESULT.format(sent=sent, failed=failed),
        reply_markup=superadmin_kb(message.from_user.id),
    )


@router.message(F.text == texts.BTN_SYNC_TELEGRAM_IDS)
async def sync_telegram_ids(message: Message) -> None:
    await message.answer(texts.SYNC_RUNNING)
    try:
        result = await panel_client.sync_telegram_ids()
    except PanelClientError as exc:
        await message.answer(
            texts.SYNC_FAILED.format(error=exc), reply_markup=superadmin_kb(message.from_user.id)
        )
        return

    updated = result.get("updated") or []
    if not updated:
        await message.answer(texts.SYNC_RESULT_NONE, reply_markup=superadmin_kb(message.from_user.id))
        return

    text = texts.SYNC_RESULT_HEADER.format(count=len(updated))
    for a in updated:
        text += texts.SYNC_RESULT_LINE.format(username=a["username"], telegram_id=a["telegram_id"])
    await message.answer(text, reply_markup=superadmin_kb(message.from_user.id))


# ---- add panel via bot --------------------------------------------------------

@router.message(F.text == texts.BTN_ADD_PANEL)
async def start_create_panel(message: Message, state: FSMContext) -> None:
    await state.set_state(CreatePanel.name)
    await message.answer(texts.ASK_PANEL_NAME, reply_markup=keyboards.cancel_kb())


@router.message(CreatePanel.name, ~F.text.in_(ALL_MENU_TEXTS))
async def create_panel_name(message: Message, state: FSMContext) -> None:
    name = (message.text or "").strip()
    if not name:
        await message.answer(texts.ASK_PANEL_NAME)
        return
    await state.update_data(panel_name=name)
    await state.set_state(CreatePanel.url)
    await message.answer(texts.ASK_PANEL_URL, reply_markup=keyboards.cancel_kb())


@router.message(CreatePanel.url, ~F.text.in_(ALL_MENU_TEXTS))
async def create_panel_url(message: Message, state: FSMContext) -> None:
    url = (message.text or "").strip()
    if not url:
        await message.answer(texts.ASK_PANEL_URL)
        return
    await state.update_data(panel_url=url)
    await state.set_state(CreatePanel.username)
    await message.answer(texts.ASK_PANEL_ADMIN_USER, reply_markup=keyboards.cancel_kb())


@router.message(CreatePanel.username, ~F.text.in_(ALL_MENU_TEXTS))
async def create_panel_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.ASK_PANEL_ADMIN_USER)
        return
    await state.update_data(panel_admin_user=username)
    await state.set_state(CreatePanel.password)
    await message.answer(texts.ASK_PANEL_ADMIN_PASS, reply_markup=keyboards.cancel_kb())


@router.message(CreatePanel.password, ~F.text.in_(ALL_MENU_TEXTS))
async def create_panel_finish(message: Message, state: FSMContext) -> None:
    password = (message.text or "").strip()
    if not password:
        await message.answer(texts.ASK_PANEL_ADMIN_PASS)
        return
    data = await state.get_data()
    await state.clear()
    await message.answer(texts.CREATING_PANEL)

    try:
        result = await panel_client.create_panel(
            name=data["panel_name"],
            url=data["panel_url"],
            username=data["panel_admin_user"],
            password=password,
        )
    except PanelClientError as exc:
        await message.answer(
            texts.PANEL_CREATED_FAIL.format(error=exc),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return

    await message.answer(
        texts.PANEL_CREATED_OK.format(name=result["name"]),
        reply_markup=superadmin_kb(message.from_user.id),
    )


# ---- per-admin pricing -------------------------------------------------------

@router.message(F.text == texts.BTN_SET_ADMIN_PRICE)
async def start_set_admin_price(message: Message, state: FSMContext) -> None:
    await state.set_state(SetAdminPrice.admin_username)
    await message.answer(texts.ASK_ADMIN_FOR_PRICE, reply_markup=keyboards.cancel_kb())


@router.message(SetAdminPrice.admin_username, ~F.text.in_(ALL_MENU_TEXTS))
async def get_admin_price_username(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.ASK_ADMIN_FOR_PRICE)
        return
    # Verify admin exists via panel's ORM
    with sessionLocal() as session:
        admin_obj = crud.get_admin_by_username(session, username)
    if not admin_obj:
        await state.clear()
        await message.answer(
            texts.ADMIN_NOT_FOUND.format(admin=username),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return
    current = db.get_admin_price(username)
    current_text = f"\nقیمت فعلی: {current:,} تومان" if current is not None else ""
    await state.update_data(admin_price_target=username)
    await state.set_state(SetAdminPrice.price)
    await message.answer(
        texts.ASK_ADMIN_PRICE_VALUE.format(admin=username) + current_text,
        reply_markup=keyboards.cancel_kb(),
    )


@router.message(SetAdminPrice.price, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_set_admin_price(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace(",", "")
    try:
        price = float(raw)
        if price < 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.INVALID_PRICE, reply_markup=superadmin_kb(message.from_user.id))
        return
    data = await state.get_data()
    await state.clear()
    admin = data["admin_price_target"]
    if price == 0:
        db.remove_admin_price(admin)
        await message.answer(
            texts.ADMIN_PRICE_CLEARED.format(admin=admin),
            reply_markup=superadmin_kb(message.from_user.id),
        )
    else:
        db.set_admin_price(admin, price)
        await message.answer(
            texts.ADMIN_PRICE_SET.format(admin=admin, price=int(price)),
            reply_markup=superadmin_kb(message.from_user.id),
        )


@router.message(F.text == texts.BTN_LIST_ADMIN_PRICE)
async def list_admin_prices(message: Message) -> None:
    with db._connect() as conn:
        rows = conn.execute(
            "SELECT admin_username, price_per_gb FROM admin_prices ORDER BY admin_username"
        ).fetchall()
    if not rows:
        await message.answer(texts.ADMIN_PRICES_NONE, reply_markup=superadmin_kb(message.from_user.id))
        return
    lines = [texts.ADMIN_PRICE_LINE.format(admin=r["admin_username"], price=int(r["price_per_gb"])) for r in rows]
    await message.answer(
        texts.ADMIN_PRICES_LIST.format(lines="\n".join(lines)),
        reply_markup=superadmin_kb(message.from_user.id),
    )


@router.message(F.text == texts.BTN_CLEAR_ADMIN_PRICE)
async def start_clear_admin_price(message: Message, state: FSMContext) -> None:
    await state.set_state(ClearAdminPrice.admin_username)
    await message.answer(texts.ASK_ADMIN_FOR_PRICE, reply_markup=keyboards.cancel_kb())


@router.message(ClearAdminPrice.admin_username, ~F.text.in_(ALL_MENU_TEXTS))
async def finish_clear_admin_price(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.ASK_ADMIN_FOR_PRICE)
        return
    current = db.get_admin_price(username)
    if current is None:
        await state.clear()
        await message.answer(
            texts.ADMIN_NOT_FOUND.format(admin=username),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return
    db.remove_admin_price(username)
    await state.clear()
    await message.answer(
        texts.ADMIN_PRICE_CLEARED.format(admin=username),
        reply_markup=superadmin_kb(message.from_user.id),
    )


# ---------------------------------------------------------------------------
# Referral code management
# ---------------------------------------------------------------------------

@router.message(F.text == texts.BTN_MANAGE_REFERRALS)
async def start_manage_referrals(message: Message) -> None:
    codes = db.list_referral_codes()
    if not codes:
        await message.answer(
            texts.REFERRAL_CODES_NONE,
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return
    lines = [
        texts.REFERRAL_CODE_LINE.format(
            code=c["code"],
            owner=c["owner_telegram_id"],
            bonus=c["bonus_percent"],
            price=int(c["price_per_gb"]),
            status="فعال" if c["enabled"] else "غیرفعال",
        )
        for c in codes
    ]
    await message.answer(
        texts.REFERRAL_CODES_HEADER + "\n".join(lines),
        reply_markup=superadmin_kb(message.from_user.id),
    )


@router.message(F.text == texts.BTN_ADD_REFERRAL_CODE)
async def start_add_referral(message: Message, state: FSMContext) -> None:
    await state.set_state(ReferralManage.owner)
    await message.answer(texts.REFERRAL_ASK_OWNER, reply_markup=keyboards.cancel_kb())


@router.message(ReferralManage.owner, ~F.text.in_(ALL_MENU_TEXTS))
async def get_referral_owner(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip()
    if not raw.lstrip("-").isdigit():
        await message.answer(texts.REFERRAL_ASK_OWNER)
        return
    await state.update_data(ref_owner=int(raw))
    await state.set_state(ReferralManage.code)
    await message.answer(texts.REFERRAL_ASK_CODE_STR, reply_markup=keyboards.cancel_kb())


@router.message(ReferralManage.code, ~F.text.in_(ALL_MENU_TEXTS))
async def get_referral_code_str(message: Message, state: FSMContext) -> None:
    code = (message.text or "").strip()
    if not code:
        await message.answer(texts.REFERRAL_ASK_CODE_STR)
        return
    await state.update_data(ref_code=code)
    await state.set_state(ReferralManage.bonus)
    await message.answer(texts.REFERRAL_ASK_BONUS, reply_markup=keyboards.cancel_kb())


@router.message(ReferralManage.bonus, ~F.text.in_(ALL_MENU_TEXTS))
async def get_referral_bonus(message: Message, state: FSMContext) -> None:
    raw = (message.text or "").strip().replace("%", "")
    try:
        bonus = float(raw)
        if bonus <= 0 or bonus > 100:
            raise ValueError
    except ValueError:
        await message.answer(texts.REFERRAL_ASK_BONUS)
        return
    await state.update_data(ref_bonus=bonus)
    await state.set_state(ReferralManage.price)
    await message.answer(texts.REFERRAL_ASK_PRICE, reply_markup=keyboards.cancel_kb())


@router.message(ReferralManage.price, ~F.text.in_(ALL_MENU_TEXTS))
async def get_referral_price(message: Message, state: FSMContext, bot: Bot) -> None:
    raw = (message.text or "").strip().replace(",", "")
    try:
        price = float(raw)
        if price <= 0:
            raise ValueError
    except ValueError:
        await message.answer(texts.REFERRAL_ASK_PRICE)
        return

    data = await state.get_data()
    await state.clear()

    db.create_referral_code(
        telegram_id=data["ref_owner"],
        code=data["ref_code"],
        bonus_percent=data["ref_bonus"],
        price_per_gb=price,
    )
    await message.answer(
        texts.REFERRAL_CREATED,
        reply_markup=superadmin_kb(message.from_user.id),
    )

    # Notify the referral owner about their new code
    owner_tid = data["ref_owner"]
    try:
        await bot.send_message(
            owner_tid,
            texts.REFERRAL_REQUEST_APPROVED_NOTIFY.format(
                code=data["ref_code"],
                bonus=int(data["ref_bonus"]),
                price=int(price),
            ),
        )
    except Exception:
        pass


# ---------------------------------------------------------------------------
# Delete admin (panel)
# ---------------------------------------------------------------------------

@router.message(F.text == texts.BTN_DELETE_ADMIN)
async def start_delete_admin(message: Message, state: FSMContext) -> None:
    await state.set_state(DeleteAdmin.username)
    await message.answer(texts.DELETE_ADMIN_ASK, reply_markup=keyboards.cancel_kb())


@router.message(DeleteAdmin.username, ~F.text.in_(ALL_MENU_TEXTS))
async def confirm_delete_admin(message: Message, state: FSMContext) -> None:
    username = (message.text or "").strip()
    if not username:
        await message.answer(texts.DELETE_ADMIN_ASK)
        return
    with sessionLocal() as session:
        admin_obj = crud.get_admin_by_username(session, username)
    if not admin_obj:
        await state.clear()
        await message.answer(
            texts.ADMIN_NOT_FOUND.format(admin=username),
            reply_markup=superadmin_kb(message.from_user.id),
        )
        return
    await state.update_data(delete_admin_target=username)
    await message.answer(
        texts.DELETE_ADMIN_CONFIRM.format(username=username),
        reply_markup=keyboards.delete_admin_confirm_kb(username),
    )


@router.callback_query(F.data.startswith("del_admin_yes:"))
async def finish_delete_admin(call: CallbackQuery, state: FSMContext) -> None:
    username = call.data.split(":", 1)[1]
    await state.clear()
    await call.answer()

    try:
        from backend.bot import panel_client
        result = await panel_client.delete_admin_by_username(username)
    except Exception as exc:
        await call.message.answer(
            texts.DELETE_ADMIN_FAILED.format(error=exc),
            reply_markup=superadmin_kb(call.from_user.id),
        )
        return

    # Notify superadmin
    await call.message.answer(
        texts.DELETE_ADMIN_SUCCESS_SUPERADMIN.format(username=username),
        reply_markup=superadmin_kb(call.from_user.id),
    )

    # Notify owner if they have a telegram_id — simple message, no Marzban note
    telegram_id = result.get("telegram_id")
    if telegram_id:
        try:
            await call.bot.send_message(
                telegram_id,
                texts.DELETE_ADMIN_SUCCESS_OWNER.format(username=username),
            )
        except Exception:
            pass


@router.callback_query(F.data == "del_admin_no")
async def cancel_delete_admin(call: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await call.answer("لغو شد")
    await call.message.answer(
        texts.CANCELLED,
        reply_markup=superadmin_kb(call.from_user.id),
    )
