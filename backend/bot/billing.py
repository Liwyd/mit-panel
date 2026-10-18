"""Money movement between a person's wallet and their panels' weekly debts."""

from __future__ import annotations

from backend.bot import db


def apply_wallet_to_debts(
    telegram_id: int, skip_usernames: set[str] | None = None
) -> list[dict]:
    """Pay down this person's outstanding debts from their wallet, oldest panel
    first, spending only what the wallet actually holds.

    `skip_usernames` leaves those panels' debts alone entirely — the weekly
    settlement passes the observer set so a frozen panel's debt is neither
    drained nor partially settled behind the superadmin's back.

    Returns one entry per debt touched: {username, paid, remaining}.
    """
    results: list[dict] = []
    for debt in db.list_outstanding_debts():
        if debt["telegram_id"] != telegram_id:
            continue
        if skip_usernames and debt["username"] in skip_usernames:
            continue
        if db.get_wallet_balance(telegram_id) <= 0:
            break
        paid = db.drain_wallet(telegram_id, debt["amount"])
        if paid <= 0:
            continue
        remaining = db.reduce_debt(debt["username"], paid)
        db.record_sale(
            telegram_id=telegram_id,
            username=debt["username"],
            gb=0,
            amount=paid,
            method=db.SETTLEMENT_METHOD,
        )
        results.append({"username": debt["username"], "paid": paid, "remaining": remaining})
    return results
