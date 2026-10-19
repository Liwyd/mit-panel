"""What approving a receipt actually does.

Shared by the superadmin's Approve button and the automatic approver, so both
move exactly the same money in exactly the same way.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from aiogram import Bot

from backend.bot import texts
from backend.bot import db
from backend.bot.billing import apply_wallet_to_debts
from backend.bot.panel_client import PanelClientError
from backend.bot import panel_client
from backend.bot.units import bytes_to_gb

# reviewed_by for an approval nobody pressed a button for.
AUTOMATIC = 0


@dataclass
class Outcome:
    ok: bool
    message: str
    alert: bool = False
    # Whether the receipt's buttons are now pointless and should come off.
    finished: bool = False


async def _tell(bot: Bot, chat_id: int, text: str) -> None:
    try:
        await bot.send_message(chat_id, text)
    except Exception:
        pass


async def approve_request(bot: Bot, request_id: int, reviewer_id: int) -> Outcome:
    req = db.get_request(request_id)
    if req is None:
        return Outcome(False, texts.NOT_FOUND, alert=True)
    # The atomic pending -> approved flip is the double-credit guard: nothing
    # below can run twice for the same receipt, however it was approved.
    if not db.mark_reviewed(request_id, status="approved", reviewed_by=reviewer_id):
        return Outcome(False, texts.ALREADY_HANDLED, alert=True)

    # Clean up receipt file after successful status change
    if req.receipt_path:
        try:
            os.unlink(req.receipt_path)
        except OSError:
            pass

    customer = req.admin_telegram_id

    if req.kind == "wallet":
        db.add_wallet_balance(customer, req.toman_amount)
        db.record_sale(
            telegram_id=customer,
            username=None,
            gb=0,
            amount=req.toman_amount,
            method=db.WALLET_CHARGE_METHOD,
        )
        # Newly arrived money clears any outstanding weekly debt immediately.
        apply_wallet_to_debts(customer)
        await _tell(
            bot,
            customer,
            texts.WALLET_CHARGED_ADMIN.format(
                amount=req.toman_amount, balance=db.get_wallet_balance(customer)
            ),
        )
        return Outcome(True, texts.APPROVED_TOAST, finished=True)

    if req.kind == "invoice":
        if not db.mark_invoice_paid(req.invoice_id):
            return Outcome(False, texts.INVOICE_ALREADY_PAID, alert=True, finished=True)
        db.record_sale(
            telegram_id=customer, username=None, gb=0, amount=req.toman_amount, method="invoice"
        )

        invoice = db.get_invoice(req.invoice_id) if req.invoice_id else None
        # An invoice raised by the usage sync buys GB back for one panel. Paying
        # it has to credit that panel, or the reseller is left in debt with an
        # invoice marked paid and no way to sell configs again.
        grants_gb = bool(invoice and invoice.admin_username and invoice.traffic_gb > 0)
        if grants_gb:
            try:
                await panel_client.topup(
                    customer, invoice.traffic_gb, username=invoice.admin_username
                )
            except PanelClientError as exc:
                # Money was taken but nothing was credited: undo both records
                # so the receipt can be approved again rather than vanishing.
                db.revert_invoice_to_pending(invoice.id)
                db.revert_to_pending(request_id)
                return Outcome(False, f"{texts.PANEL_ERROR_TOAST} ({exc})", alert=True)

        await _tell(
            bot,
            customer,
            texts.USAGE_SYNC_PAID_CUSTOMER
            if grants_gb
            else texts.INVOICE_PAID_CUSTOMER.format(id=req.invoice_id),
        )
        return Outcome(True, texts.APPROVED_TOAST, finished=True)

    if req.kind == "settlement":
        # Pay down by what the receipt covers instead of wiping the debt: it may
        # have grown since they started paying, or shrunk as the wallet chipped
        # in. Anything beyond what was owed lands in their wallet, not nowhere.
        owed = db.get_debt(req.admin_username)
        remaining = db.reduce_debt(req.admin_username, req.toman_amount)
        excess = max(0, req.toman_amount - owed)
        if excess:
            db.add_wallet_balance(customer, excess)
        # Only what actually went against the debt: the excess is wallet credit.
        applied = min(owed, req.toman_amount)
        if applied > 0:
            db.record_sale(
                telegram_id=customer,
                username=req.admin_username,
                gb=0,
                amount=applied,
                method=db.SETTLEMENT_METHOD,
            )

        if remaining > 0:
            text = texts.SETTLEMENT_PARTIAL_ADMIN.format(
                username=req.admin_username, paid=req.toman_amount, remaining=remaining
            )
        elif excess:
            text = texts.SETTLEMENT_APPROVED_WITH_CREDIT.format(
                username=req.admin_username,
                excess=excess,
                balance=db.get_wallet_balance(customer),
            )
        else:
            text = texts.SETTLEMENT_APPROVED_ADMIN.format(username=req.admin_username)
        await _tell(bot, customer, text)
        return Outcome(True, texts.APPROVED_TOAST, finished=True)

    try:
        result = await panel_client.topup(customer, req.requested_gb, username=req.admin_username)
    except PanelClientError as exc:
        db.revert_to_pending(request_id)
        return Outcome(False, f"{texts.PANEL_ERROR_TOAST} ({exc})", alert=True)

    # A successful top-up rearms the low-traffic warnings for this panel.
    db.clear_warning_bucket(req.admin_username)
    db.record_sale(
        telegram_id=customer,
        username=req.admin_username,
        gb=req.requested_gb,
        amount=req.toman_amount,
        method="card",
    )
    await _tell(
        bot,
        customer,
        texts.REQUEST_APPROVED_ADMIN.format(
            added_gb=req.requested_gb,
            new_balance_gb=bytes_to_gb(result.get("new_traffic_bytes")),
        ),
    )
    return Outcome(True, texts.APPROVED_TOAST, finished=True)
