"""What approving a receipt actually does.

Shared by the superadmin's Approve button and the automatic approver, so both
move exactly the same money in exactly the same way.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from aiogram import Bot

from backend.bot import black_friday, texts
from backend.bot import db
from backend.bot import access_lock
from backend.bot.billing import apply_wallet_to_debts
from backend.bot.panel_client import PanelClientError
from backend.bot import panel_client
from backend.bot.units import bytes_to_gb
from backend.db import crud
from backend.db.engin import sessionLocal

logger = logging.getLogger(__name__)

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


def _usernames_for(telegram_id: int) -> list[str]:
    with sessionLocal() as session:
        return [a.username for a in crud.get_admins_by_telegram_id(session, telegram_id)]


async def _maybe_unlock(
    bot: Bot, admin_username: str | None, telegram_id: int | None = None
) -> None:
    """Hand access back the moment payment clears everything owed.

    The 5-minute monitor would get there eventually; doing it here means the
    admin's dashboard is usable again by the time they see the paid toast.
    Failures only delay — never block — the approval itself.
    """
    try:
        if admin_username:
            await access_lock.release_if_clear(bot, admin_username)
            return
        if telegram_id is not None:
            for username in _usernames_for(telegram_id):
                await access_lock.release_if_clear(bot, username)
    except Exception:
        logger.exception("post-payment unlock check failed")


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
        await _maybe_unlock(bot, None, customer)
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

        # Booked only now that nothing can revert this approval, so a failed
        # grant followed by a re-approval cannot count the payment twice. An
        # invoice is booked under its panel with the GB it sold (see
        # db.invoice_ledger_fields), so the profit report can cost it.
        panel, sold_gb = db.invoice_ledger_fields(invoice, grants_gb)
        db.record_sale(
            telegram_id=customer,
            username=panel,
            gb=sold_gb,
            amount=req.toman_amount,
            method="invoice",
        )

        # Paid at the Black Friday rate: note it for the event's stats, now that
        # nothing can still revert this approval. Only requests raised by the
        # event's flow carry a credit amount. No ledger discount row: invoice
        # revenue is booked at payment, already at the event price.
        if req.bf_credit_amount:
            if req.bf_credit_amount - req.toman_amount > 0:
                black_friday.record_purchase(
                    telegram_id=customer,
                    username=invoice.admin_username if invoice else None,
                    kind=black_friday.PURCHASE_INVOICE,
                    amount=req.toman_amount,
                    list_amount=req.bf_credit_amount,
                    method=black_friday.METHOD_CARD,
                )

        await _tell(
            bot,
            customer,
            texts.USAGE_SYNC_PAID_CUSTOMER
            if grants_gb
            else texts.INVOICE_PAID_CUSTOMER.format(id=req.invoice_id),
        )
        await _maybe_unlock(bot, invoice.admin_username if invoice else None, customer)
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
        await _maybe_unlock(bot, req.admin_username)
        return Outcome(True, texts.APPROVED_TOAST, finished=True)

    if req.kind == black_friday.KIND_SETTLEMENT:
        # Paid at the event rate for a debt that may have moved since the
        # receipt was sent: settle_debt re-reads what is owed, retires no more
        # than that, and puts any money it could not apply into the wallet.
        paid = req.toman_amount
        result = black_friday.settle_debt(
            customer, req.admin_username, paid, req.bf_credit_amount or 0,
            black_friday.METHOD_CARD,
        )
        text = texts.BF_SETTLEMENT_APPROVED_ADMIN.format(
            paid=paid, username=req.admin_username, cancelled=result.cancelled
        )
        if result.remaining > 0:
            text += texts.BF_SETTLEMENT_REMAINING.format(remaining=result.remaining)
        if result.excess:
            text += texts.BF_SETTLEMENT_EXCESS.format(
                excess=result.excess, balance=db.get_wallet_balance(customer)
            )
        await _tell(bot, customer, text)
        await _maybe_unlock(bot, req.admin_username)
        return Outcome(True, texts.APPROVED_TOAST, finished=True)

    if req.kind not in ("topup", black_friday.KIND_TOPUP):
        # A kind this code does not know must not fall through to granting
        # traffic. Put it back so it is neither lost nor half-handled.
        logger.error("request #%s has an unknown kind %r", request_id, req.kind)
        db.revert_to_pending(request_id)
        return Outcome(False, texts.PANEL_ERROR_TOAST, alert=True)

    try:
        result = await panel_client.topup(customer, req.requested_gb, username=req.admin_username)
    except PanelClientError as exc:
        db.revert_to_pending(request_id)
        return Outcome(False, f"{texts.PANEL_ERROR_TOAST} ({exc})", alert=True)

    if req.kind == black_friday.KIND_TOPUP:
        # Same grant as a normal top-up, at the price locked into the request —
        # honoured even if the event has ended since.
        db.clear_warning_bucket(req.admin_username)
        db.record_sale(
            telegram_id=customer,
            username=req.admin_username,
            gb=req.requested_gb,
            amount=req.toman_amount,
            method=db.BF_CARD_METHOD,
        )
        paid_gb = req.bf_paid_gb if req.bf_paid_gb is not None else req.requested_gb
        gift_gb = req.bf_gift_gb or 0.0
        black_friday.record_purchase(
            telegram_id=customer,
            username=req.admin_username,
            kind=black_friday.PURCHASE_TOPUP,
            paid_gb=paid_gb,
            gift_gb=gift_gb,
            amount=req.toman_amount,
            list_amount=req.bf_credit_amount or req.toman_amount,
            method=black_friday.METHOD_CARD,
        )
        await _tell(
            bot,
            customer,
            texts.BF_TOPUP_APPROVED_ADMIN.format(
                paid_gb=paid_gb,
                gift_part=texts.BF_GIFT_PART.format(gift_gb=gift_gb) if gift_gb else "",
                added_gb=req.requested_gb,
                new_balance_gb=bytes_to_gb(result.get("new_traffic_bytes")),
            ),
        )
        return Outcome(True, texts.APPROVED_TOAST, finished=True)

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


async def reject_request(
    bot: Bot, request_id: int, reviewer_id: int, reason: str | None = None
) -> Outcome:
    """Reject a pending receipt using the same atomic guard as Telegram.

    The dashboard and Telegram are two review surfaces for one queue.  Keeping
    the status transition here prevents either surface from winning twice when
    two reviewers act at nearly the same time.
    """
    req = db.get_request(request_id)
    if req is None:
        return Outcome(False, texts.NOT_FOUND, alert=True)
    if not db.mark_reviewed(request_id, status="rejected", reviewed_by=reviewer_id, reason=reason):
        return Outcome(False, texts.ALREADY_HANDLED, alert=True)

    if req.receipt_path:
        try:
            os.unlink(req.receipt_path)
        except OSError:
            pass

    text = (
        texts.REQUEST_REJECTED_ADMIN_WITH_REASON.format(reason=reason)
        if reason
        else texts.REQUEST_REJECTED_ADMIN
    )
    await _tell(bot, req.admin_telegram_id, text)
    return Outcome(True, texts.REJECTED_TOAST, finished=True)
