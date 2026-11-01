"""Native Top-up bot management endpoints for mit-panel.
Queries mit-panel settings store and database directly.
"""

import json
import os
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse

from backend.auth.auth import get_current_admin
from backend.schema.output import ResponseModel
from backend.utils.settings_store import get_settings, update_settings, DATA_DIR
from backend.bot import db

router = APIRouter(prefix="/topup-bot", tags=["Top-up bot"])

TOPUP_CONFIG_PATH = os.path.join(DATA_DIR, "topup_config.json")


def _get_topup_config() -> dict:
    try:
        if os.path.exists(TOPUP_CONFIG_PATH):
            with open(TOPUP_CONFIG_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, dict):
                    return data
    except Exception:
        pass
    return {
        "settings": {},
        "texts": {},
        "buttons": {},
    }


def _save_topup_config(cfg: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = TOPUP_CONFIG_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(cfg, f, ensure_ascii=False, indent=2)
    os.replace(tmp, TOPUP_CONFIG_PATH)


def _fail(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"success": False, "message": message})


def _superadmin_only(user: dict) -> JSONResponse | None:
    if user.get("role") != "superadmin":
        return _fail(403, "Access denied. Only superadmin can access this endpoint")
    return None


@router.get("/connection", description="Native connection status")
async def get_connection(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    st = get_settings()
    return ResponseModel(
        success=True,
        message="ok",
        data={
            "url": "builtin",
            "own_key": True,
            "connected": True,
            "error": None,
            "bot_username": "mitpanelbot",
            "bot_name": "MIT TOPUP-bot",
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
            "bot_name": "MIT TOPUP-bot",
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
            "bot_name": "MIT TOPUP-bot",
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
    cfg = _get_topup_config()
    settings_data = cfg.get("settings", {})
    
    # Fetch real settings from db/settings_store
    card_number = db.get_setting("card_number") or ""
    price_str = db.get_setting("price_per_gb")
    try:
        price_per_gb = float(price_str) if price_str else 10000.0
    except Exception:
        price_per_gb = 10000.0

    settings_data.setdefault("price_per_gb", price_per_gb)
    settings_data.setdefault("card_number", card_number)
    settings_data.setdefault("force_join_enabled", False)
    settings_data.setdefault("force_join_channel", "")
    settings_data.setdefault("auto_approve_enabled", False)
    settings_data.setdefault("has_bulk_pin", False)
    settings_data.setdefault("min_gb", 1)
    settings_data.setdefault("max_gb", 100)

    return ResponseModel(success=True, message="ok", data=settings_data)


@router.put("/api/settings", description="Update bot settings")
async def api_update_settings(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    cfg = _get_topup_config()
    cfg["settings"] = {**cfg.get("settings", {}), **body}
    _save_topup_config(cfg)
    
    if "card_number" in body:
        db.set_setting("card_number", str(body["card_number"]))
    if "price_per_gb" in body:
        db.set_setting("price_per_gb", str(body["price_per_gb"]))

    return ResponseModel(success=True, message="Updated", data=cfg["settings"])


@router.get("/api/texts", description="Bot texts")
async def api_texts(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    cfg = _get_topup_config()
    stored_texts = cfg.get("texts", {})
    
    default_texts = [
        {"id": "welcome", "text": "سلام! به ربات شارژ و مدیریت پنل خوش آمدید.", "default": "سلام! به ربات شارژ و مدیریت پنل خوش آمدید.", "changed": "welcome" in stored_texts, "button": False, "plain": False, "fields": []},
        {"id": "ask_amount", "text": "لطفاً مقدار حجم مورد نیاز (گیگابایت) را وارد کنید:", "default": "لطفاً مقدار حجم مورد نیاز (گیگابایت) را وارد کنید:", "changed": "ask_amount" in stored_texts, "button": False, "plain": False, "fields": []},
        {"id": "payment_card", "text": "لطفاً مبلغ {amount:,} تومان را به کارت زیر واریز نمایید:\n\n<code>{card_number}</code>", "default": "لطفاً مبلغ {amount:,} تومان را به کارت زیر واریز نمایید:\n\n<code>{card_number}</code>", "changed": "payment_card" in stored_texts, "button": False, "plain": False, "fields": ["amount", "card_number"]},
    ]
    
    result = []
    for dt in default_texts:
        tid = dt["id"]
        if tid in stored_texts:
            dt["text"] = stored_texts[tid]
            dt["changed"] = True
        result.append(dt)
    return ResponseModel(success=True, message="ok", data=result)


@router.put("/api/texts", description="Update bot texts")
async def api_update_texts(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    cfg = _get_topup_config()
    if "texts" not in cfg:
        cfg["texts"] = {}
    if isinstance(body, dict):
        cfg["texts"].update(body)
    _save_topup_config(cfg)
    return ResponseModel(success=True, message="Updated", data={})


@router.get("/api/buttons", description="Bot buttons")
async def api_buttons(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    cfg = _get_topup_config()
    buttons_data = cfg.get("buttons", {})
    if not buttons_data or not buttons_data.get("buttons"):
        buttons_data = {
            "buttons": {
                "topup": {"style": "default", "emoji": ""},
                "support": {"style": "default", "emoji": ""},
            },
            "labels": {
                "topup": "شارژ حجم",
                "support": "پشتیبانی",
            },
            "defaults": {
                "topup": "default",
                "support": "default",
            },
            "styles": ["default", "primary", "success", "danger"],
        }
    return ResponseModel(success=True, message="ok", data=buttons_data)


@router.put("/api/buttons", description="Update bot buttons")
async def api_update_buttons(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    cfg = _get_topup_config()
    cfg["buttons"] = {**cfg.get("buttons", {}), **body}
    _save_topup_config(cfg)
    return ResponseModel(success=True, message="Updated", data=cfg["buttons"])
