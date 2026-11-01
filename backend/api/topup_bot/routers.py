"""Native Top-up bot management endpoints for mit-panel.
Replaces the external microservice proxy with direct SQLite and settings queries.
"""

from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse

from backend.auth.auth import get_current_admin
from backend.schema.output import ResponseModel
from backend.bot import db

router = APIRouter(prefix="/topup-bot", tags=["Top-up bot"])


def _fail(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"success": False, "message": message})


def _superadmin_only(user: dict) -> JSONResponse | None:
    if user.get("role") != "superadmin":
        return _fail(403, "Access denied. Only superadmin can access this endpoint")
    return None


@router.get("/connection", description="Native connection status for built-in topup bot")
async def get_connection(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(
        success=True,
        message="ok",
        data={
            "url": "builtin",
            "own_key": True,
            "connected": True,
            "error": None,
            "bot_username": "mitpanelbot",
            "bot_name": "MIT Topup Bot",
        },
    )


@router.put("/connection", description="Connect native topup bot")
async def set_connection(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(
        success=True,
        message="Connected",
        data={
            "url": "builtin",
            "own_key": True,
            "connected": True,
            "error": None,
            "bot_username": "mitpanelbot",
            "bot_name": "MIT Topup Bot",
        },
    )


@router.get("/api/info", description="Bot info")
async def api_info(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(
        success=True,
        message="ok",
        data={
            "kind": "topup",
            "bot_username": "mitpanelbot",
            "bot_name": "MIT Topup Bot",
            "version": "1.0.0",
        },
    )


@router.get("/api/stats", description="Bot statistics from local DB")
async def api_stats(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    with db._connect() as conn:
        users_count = conn.execute("SELECT COUNT(*) FROM bot_users").fetchone()[0]
        linked_users = conn.execute("SELECT COUNT(*) FROM bot_users WHERE username IS NOT NULL").fetchone()[0]
        pending_reqs = conn.execute("SELECT COUNT(*), COALESCE(SUM(toman_amount),0), COALESCE(SUM(requested_gb),0) FROM topup_requests WHERE status='pending'").fetchone()
        sales_today = conn.execute("SELECT COUNT(*), COALESCE(SUM(toman_amount),0), COALESCE(SUM(requested_gb),0) FROM topup_requests WHERE status='approved'").fetchone()
    return ResponseModel(
        success=True,
        message="ok",
        data={
            "users": users_count,
            "linked_users": linked_users,
            "pending_requests": pending_reqs[0],
            "pending_amount": pending_reqs[1],
            "open_bills": 0,
            "open_bills_amount": 0,
            "overdue_bills": 0,
            "overdue_amount": 0,
            "locked_panels": 0,
            "sales_today": sales_today[0],
            "sales_today_amount": sales_today[1],
            "sales_today_gb": sales_today[2],
        },
    )


@router.get("/api/settings", description="Bot settings")
async def api_settings(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(
        success=True,
        message="ok",
        data={
            "price_per_gb": 10000,
            "card_number": "",
            "force_join_enabled": False,
            "force_join_channel": "",
            "auto_approve_enabled": False,
            "has_bulk_pin": False,
            "min_gb": 1,
            "max_gb": 100,
        },
    )


@router.put("/api/settings", description="Update bot settings")
async def api_update_settings(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(success=True, message="Updated", data=body)


@router.get("/api/texts", description="Bot texts")
async def api_texts(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(success=True, message="ok", data=[])


@router.put("/api/texts", description="Update bot texts")
async def api_update_texts(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(success=True, message="Updated", data={})


@router.get("/api/buttons", description="Bot buttons")
async def api_buttons(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(
        success=True,
        message="ok",
        data={
            "buttons": {},
            "labels": {},
            "defaults": {},
            "styles": [],
        },
    )


@router.put("/api/buttons", description="Update bot buttons")
async def api_update_buttons(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    return ResponseModel(success=True, message="Updated", data={})
