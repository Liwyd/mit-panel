"""Management API for the built-in Telegram top-up bot.

The bot runs in this process and owns its financial state in
``backend.bot.db``.  These endpoints expose that live state and call the same
approval logic as Telegram; no proxy or shadow configuration is involved.
"""

from __future__ import annotations

import os
from datetime import datetime, time, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse, JSONResponse

from backend.auth.auth import get_current_admin
from backend.bot import auto_approve, db
from backend.bot.config import bot_config
from backend.bot.content import DEFAULT_TEXTS, apply_text_overrides, configured_overrides, fields
from backend.bot.service import is_running
from backend.schema.output import ResponseModel
from backend.utils.settings_store import get_settings, update_settings

router = APIRouter(prefix="/topup-bot", tags=["Top-up bot"])

_TEHRAN = ZoneInfo("Asia/Tehran")
_WEB_REVIEWER = -1  # distinct from Telegram users and automatic approval (0)


def _fail(message: str) -> ResponseModel:
    return ResponseModel(success=False, message=message)


def _superadmin_only(user: dict) -> JSONResponse | None:
    if user.get("role") != "superadmin":
        return JSONResponse(status_code=403, content={"success": False, "message": "Access denied. Only superadmin can access this endpoint"})
    return None


def _today_start_utc() -> str:
    local_start = datetime.combine(datetime.now(_TEHRAN).date(), time.min, tzinfo=_TEHRAN)
    return local_start.astimezone(timezone.utc).isoformat()


def _to_datetime(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        result = datetime.fromisoformat(value)
    except ValueError:
        return None
    return result.replace(tzinfo=timezone.utc) if result.tzinfo is None else result


def _is_overdue(value: str | None) -> bool:
    when = _to_datetime(value)
    return bool(when and when <= datetime.now(timezone.utc))


def _request_payload(req) -> dict:
    """Serialise a request without ever leaking the server receipt path."""
    return {
        "id": req.id,
        "telegram_id": req.admin_telegram_id,
        "username": req.admin_username,
        "requested_gb": req.requested_gb,
        "amount": req.toman_amount,
        "kind": req.kind,
        "invoice_id": req.invoice_id,
        "status": req.status,
        "created_at": req.created_at,
        "reviewed_at": req.reviewed_at,
        "reject_reason": req.reject_reason,
        "has_receipt": bool(req.receipt_path and Path(req.receipt_path).is_file()),
    }


async def _review_with_bot(action):
    """Use a short-lived API client so dashboard reviews notify customers too."""
    token = bot_config.bot_token
    if not token:
        return None, "The Telegram bot token is not configured."
    from aiogram import Bot
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode

    bot = Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    try:
        return await action(bot), None
    finally:
        await bot.session.close()


@router.get("/connection", description="Built-in bot runtime status")
async def get_connection(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    configured = bool(bot_config.bot_token)
    return ResponseModel(success=True, message="ok", data={
        "url": "builtin", "own_key": True, "connected": configured,
        "running": is_running(), "error": None if configured else "Bot token is not configured",
        "bot_username": None, "bot_name": "MIT TOPUP-bot",
    })


@router.get("/api/info", description="Built-in bot runtime information")
async def api_info(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(success=True, message="ok", data={
        "kind": "topup", "bot_name": "MIT TOPUP-bot", "configured": bool(bot_config.bot_token), "running": is_running(),
    })


@router.get("/api/stats", description="Live top-up bot statistics")
async def api_stats(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    db.init_db()
    invoices = db.list_pending_invoices()
    debts = db.list_outstanding_debts()
    with db._connect() as conn:
        users = conn.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        linked_users = conn.execute("SELECT COUNT(*) FROM bot_users WHERE is_linked = 1").fetchone()[0]
        pending = conn.execute("SELECT COUNT(*), COALESCE(SUM(toman_amount), 0) FROM topup_requests WHERE status = 'pending'").fetchone()
        sales = conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(amount), 0), COALESCE(SUM(gb), 0) FROM sales "
            "WHERE created_at >= ? AND method NOT IN (?, ?, ?)",
            (_today_start_utc(), db.SETTLEMENT_METHOD, db.WALLET_CHARGE_METHOD, db.GRANT_METHOD),
        ).fetchone()
    open_amount = sum(invoice.amount for invoice in invoices) + sum(debt["amount"] for debt in debts)
    overdue_invoices = [invoice for invoice in invoices if _is_overdue(invoice.due_at)]
    overdue_debts = [debt for debt in debts if _is_overdue(debt.get("overdue_since"))]
    return ResponseModel(success=True, message="ok", data={
        "configured": bool(bot_config.bot_token), "running": is_running(), "users": users, "linked_users": linked_users,
        "pending_requests": pending[0], "pending_amount": pending[1],
        "open_bills": len(invoices) + len(debts), "open_bills_amount": open_amount,
        "overdue_bills": len(overdue_invoices) + len(overdue_debts),
        "overdue_amount": sum(invoice.amount for invoice in overdue_invoices) + sum(debt["amount"] for debt in overdue_debts),
        "locked_panels": len(db.list_admin_locks()),
        "sales_today": sales[0], "sales_today_amount": sales[1], "sales_today_gb": sales[2],
    })


@router.get("/api/settings", description="Settings used by the running bot")
async def api_settings(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    price = db.get_setting("price_per_gb")
    settings = get_settings()
    return ResponseModel(success=True, message="ok", data={
        "price_per_gb": float(price) if price else None,
        "card_number": db.get_setting("card_number") or "",
        "force_join_enabled": db.get_setting("force_join_enabled") == "1",
        "force_join_channel": db.get_setting("force_join_channel") or "",
        "auto_approve_enabled": auto_approve.is_enabled(),
        "has_bulk_pin": bool(db.get_setting("bulk_password_pin")),
        "min_gb": settings["bot_min_gb"], "max_gb": settings["bot_max_gb"],
    })


@router.put("/api/settings", description="Update settings used by the running bot")
async def api_update_settings(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    allowed = {"price_per_gb", "card_number", "force_join_enabled", "force_join_channel", "auto_approve_enabled", "bulk_password_pin", "min_gb", "max_gb"}
    unknown = set(body) - allowed
    if unknown:
        return _fail(f"Unsupported settings: {', '.join(sorted(unknown))}")
    try:
        if "price_per_gb" in body:
            price = float(str(body["price_per_gb"]).replace(",", ""))
            if price <= 0:
                raise ValueError
            db.set_setting("price_per_gb", str(price))
        if "card_number" in body:
            card = str(body["card_number"]).strip()
            if not card:
                return _fail("Card number cannot be empty.")
            db.set_setting("card_number", card)
        if "force_join_channel" in body:
            channel = str(body["force_join_channel"]).strip()
            if channel and not channel.startswith("@"):
                return _fail("Force-join channel must start with @.")
            db.set_setting("force_join_channel", channel)
        if "force_join_enabled" in body:
            if body["force_join_enabled"] and not (body.get("force_join_channel") or db.get_setting("force_join_channel")):
                return _fail("Set a force-join channel before enabling the gate.")
            db.set_setting("force_join_enabled", "1" if body["force_join_enabled"] else "0")
        if "auto_approve_enabled" in body:
            auto_approve.set_enabled(bool(body["auto_approve_enabled"]))
        if "bulk_password_pin" in body and str(body["bulk_password_pin"]).strip():
            db.set_setting("bulk_password_pin", str(body["bulk_password_pin"]).strip())
        store_patch: dict[str, float] = {}
        for key in ("min_gb", "max_gb"):
            if key in body:
                value = float(body[key])
                if value <= 0:
                    raise ValueError
                store_patch[f"bot_{key}"] = value
        if store_patch:
            future = {**get_settings(), **store_patch}
            if future["bot_min_gb"] > future["bot_max_gb"]:
                return _fail("Minimum purchase volume cannot exceed the maximum.")
            update_settings(store_patch)
    except (TypeError, ValueError):
        return _fail("Enter a valid positive numeric value.")
    return await api_settings(user)


@router.get("/api/texts", description="Editable live bot messages")
async def api_texts(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    overrides = configured_overrides()
    return ResponseModel(success=True, message="ok", data=[{
        "id": name, "text": overrides.get(name, default), "default": default,
        "changed": name in overrides, "button": False, "plain": "\n" not in default, "fields": fields(default),
    } for name, default in sorted(DEFAULT_TEXTS.items())])


@router.put("/api/texts", description="Update editable live bot messages")
async def api_update_texts(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    if not isinstance(body, dict):
        return _fail("Messages must be an object.")
    overrides = configured_overrides()
    for name, value in body.items():
        if name not in DEFAULT_TEXTS or not isinstance(value, str):
            return _fail(f"Unknown message: {name}")
        if fields(value) != fields(DEFAULT_TEXTS[name]):
            return _fail(f"The placeholders in {name} must remain unchanged.")
        if value == DEFAULT_TEXTS[name]:
            overrides.pop(name, None)
        else:
            overrides[name] = value
    update_settings({"topup_text_overrides": overrides})
    apply_text_overrides()
    return await api_texts(user)


@router.get("/api/requests", description="Pending receipt-review queue")
async def api_requests(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(success=True, message="ok", data=[_request_payload(req) for req in db.list_pending_requests()])


@router.get("/api/requests/{request_id}/receipt", description="Receipt image for a pending request")
async def api_request_receipt(request_id: int, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    req = db.get_request(request_id)
    if req is None or req.status != "pending" or not req.receipt_path or not os.path.isfile(req.receipt_path):
        return JSONResponse(status_code=404, content={"success": False, "message": "Receipt not found"})
    return FileResponse(req.receipt_path)


@router.post("/api/requests/{request_id}/approve", description="Approve a pending receipt")
async def api_approve_request(request_id: int, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    from backend.bot.approvals import approve_request
    outcome, error = await _review_with_bot(lambda bot: approve_request(bot, request_id, _WEB_REVIEWER))
    if error:
        return _fail(error)
    if not outcome.ok:
        return _fail(outcome.message)
    return ResponseModel(success=True, message=outcome.message, data={"id": request_id})


@router.post("/api/requests/{request_id}/reject", description="Reject a pending receipt")
async def api_reject_request(request_id: int, body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    reason = str(body.get("reason") or "").strip() or None
    from backend.bot.approvals import reject_request
    auto_approve.hold(request_id)
    try:
        outcome, error = await _review_with_bot(lambda bot: reject_request(bot, request_id, _WEB_REVIEWER, reason))
    finally:
        auto_approve.release(request_id)
    if error:
        return _fail(error)
    if not outcome.ok:
        return _fail(outcome.message)
    return ResponseModel(success=True, message=outcome.message, data={"id": request_id})
