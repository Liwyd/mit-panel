import json
from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.schema.output import ResponseModel, AdminOutput, AdminCredentialsOutput
from backend.schema._input import (
    AdminInput,
    BotTopupInput,
    BotChangePasswordInput,
    BotGrantInput,
    BotCreateAdminInput,
)
from backend.db import crud
from backend.db.engin import get_db
from backend.auth.auth import verify_bot_api_key
from backend.services.marzban.api import APIService as MarzbanAPI
from backend.utils.logger import logger

router = APIRouter(prefix="/bot", tags=["Bot"])


def _not_linked():
    return JSONResponse(
        status_code=status.HTTP_404_NOT_FOUND,
        content={"success": False, "message": "No admin is linked to this Telegram account"},
    )


def _resolve_target(db: Session, telegram_id: int, username: str | None):
    """Pick which of this person's panels an action applies to.

    Returns (admin, error_response) — exactly one of the two is set. Passing a
    username that this Telegram account doesn't own is treated as not-found, so
    the parameter can't be used to reach into someone else's panel.
    """
    admins = crud.get_admins_by_telegram_id(db, telegram_id)
    if not admins:
        return None, _not_linked()

    if username:
        admin = crud.get_owned_admin(db, telegram_id, username)
        if not admin:
            return None, _not_linked()
        return admin, None

    if len(admins) > 1:
        return None, JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "This Telegram account owns several panels; specify which one",
            },
        )
    return admins[0], None


@router.get(
    "/admin/{telegram_id}",
    description="Every panel linked to this Telegram account (empty list if none)",
)
async def get_admins_by_telegram_id(
    telegram_id: int,
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    admins = crud.get_admins_by_telegram_id(db, telegram_id)
    if not admins:
        return _not_linked()
    return ResponseModel(
        success=True,
        message="Admins retrieved successfully",
        data=[AdminOutput.from_orm(a) for a in admins],
    )


@router.get("/admins", description="Every admin in the panel (superadmin overview)")
async def list_all_admins(
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    admins = crud.get_all_admins(db)
    return ResponseModel(
        success=True,
        message="Admins retrieved successfully",
        data=[AdminOutput.from_orm(a) for a in admins],
    )


@router.get(
    "/admins/credentials",
    description="List every admin's current Marzban password (bulk export for the superadmin)",
)
async def list_admin_credentials(
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    admins = [a for a in crud.get_all_admins(db) if a.marzban_password]
    return ResponseModel(
        success=True,
        message="Credentials retrieved successfully",
        data=[AdminCredentialsOutput.from_orm(a) for a in admins],
    )


@router.post(
    "/admins/sync-telegram-ids",
    description="Fill in missing Telegram IDs for Nexra admins from Marzban's own admin records",
)
async def sync_telegram_ids_from_marzban(
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    updated: list[dict] = []
    skipped_conflicts: list[str] = []

    marzban_panels = [p for p in crud.get_all_panels(db) if p.panel_type == "marzban"]
    for panel in marzban_panels:
        sudo_api = MarzbanAPI(url=panel.url, username=panel.username, password=panel.password)
        try:
            marzban_admins = await sudo_api.get_admins()
        except Exception as e:
            logger.error(f"Failed to fetch admins from Marzban panel {panel.name}: {e}")
            continue

        marzban_by_username = {a.get("username"): a for a in marzban_admins}
        panel_admins = [a for a in crud.get_all_admins(db) if a.panel == panel.name]

        for admin in panel_admins:
            if admin.telegram_id:
                continue  # never overwrite an ID already set (manually or otherwise)
            m = marzban_by_username.get(admin.username)
            marzban_tid = m.get("telegram_id") if m else None
            if not marzban_tid:
                continue

            admin.telegram_id = marzban_tid
            try:
                db.commit()
                updated.append({"username": admin.username, "telegram_id": marzban_tid})
            except IntegrityError:
                db.rollback()
                skipped_conflicts.append(admin.username)

    logger.info(f"Telegram ID sync from Marzban: {len(updated)} updated, {len(skipped_conflicts)} conflicts")
    return ResponseModel(
        success=True,
        message=f"{len(updated)} admin(s) updated",
        data={"updated": updated, "skipped_conflicts": skipped_conflicts},
    )


def _credit(db: Session, admin, added_gb: float, note: str):
    added_bytes = int(added_gb * 1024**3)
    crud.grant_admin_traffic(db, admin, added_bytes)
    logger.info(f"{note}: admin {admin.username} credited {added_gb} GB")
    return ResponseModel(
        success=True,
        message="Traffic increased successfully",
        data={
            "username": admin.username,
            "telegram_id": admin.telegram_id,
            "added_gb": added_gb,
            "new_traffic_bytes": admin.traffic,
            "new_initial_traffic_bytes": admin.initial_traffic,
        },
    )


@router.post("/admin/topup", description="Increase an admin's traffic balance")
async def topup_admin_traffic(
    payload: BotTopupInput,
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    admin, error = _resolve_target(db, payload.telegram_id, payload.username)
    if error:
        return error
    return _credit(db, admin, payload.added_gb, "Bot top-up")


@router.post(
    "/admin/grant",
    description="Superadmin grants traffic to a panel by username (no Telegram link needed)",
)
async def grant_admin_traffic(
    payload: BotGrantInput,
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    admin = crud.get_admin_by_username(db, payload.username)
    if not admin:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "No admin with that username"},
        )
    return _credit(db, admin, payload.added_gb, "Superadmin grant")


@router.post(
    "/admin/change-password",
    description="Change an admin's password directly in Marzban, then mirror it in Nexra",
)
async def change_admin_marzban_password(
    payload: BotChangePasswordInput,
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    admin, error = _resolve_target(db, payload.telegram_id, payload.username)
    if error:
        return error

    panel = crud.get_panel_by_name(db, admin.panel)
    if not panel or panel.panel_type != "marzban":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "This admin's panel is not a Marzban panel; the password can't be changed automatically",
            },
        )

    # Refuse to touch the sudo account Nexra itself authenticates with. Changing
    # it here would silently cut the panel off from Marzban entirely.
    if admin.username == panel.username:
        logger.warning(f"Refused bot password change for sudo account {admin.username}")
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={
                "success": False,
                "message": "This is the panel's own service account; its password can't be changed from the bot",
            },
        )

    # Prove the requester knows the current password by authenticating to Marzban
    # as that admin — the authoritative check, rather than trusting Nexra's copy.
    verify_api = MarzbanAPI(url=panel.url, username=admin.username, password=payload.current_password)
    try:
        current_ok = await verify_api.test_connection()
    except Exception as e:
        logger.error(f"Marzban unreachable while verifying password for {admin.username}: {e}")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"success": False, "message": f"Could not reach Marzban: {e}"},
        )

    if not current_ok:
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"success": False, "message": "Current password is incorrect"},
        )

    # panel.username/panel.password are the sudo Marzban credentials Nexra already
    # uses for platform-level calls — only a sudo admin can change another admin's password.
    sudo_api = MarzbanAPI(url=panel.url, username=panel.username, password=panel.password)
    try:
        marzban_status = await sudo_api.update_admin_password(admin.username, payload.new_password)
    except Exception as e:
        logger.error(f"Marzban password change failed for admin {admin.username}: {e}")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"success": False, "message": f"Could not reach Marzban: {e}"},
        )

    if marzban_status != 200:
        logger.warning(
            f"Marzban rejected password change for admin {admin.username}: status {marzban_status}"
        )
        hints = {
            401: "Nexra's stored Marzban credentials for this panel are wrong or expired.",
            403: "This panel's stored Marzban credentials are not a sudo admin.",
            404: f"Marzban has no admin named '{admin.username}'.",
            422: "Marzban rejected the request body — the panel and Marzban versions may disagree.",
        }
        detail = hints.get(marzban_status, "Unexpected response from Marzban.")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "success": False,
                "message": f"Marzban rejected the password change (status {marzban_status}). {detail}",
            },
        )

    crud.update_marzban_password(db, admin, payload.new_password)
    logger.info(f"Bot password change: admin {admin.username} updated in Marzban and Nexra")
    return ResponseModel(
        success=True,
        message="Password updated successfully in Marzban and Nexra",
        data={"telegram_id": admin.telegram_id, "username": admin.username},
    )


@router.post(
    "/admin/create",
    description="Provision a new reseller: create the admin in Marzban, then in MIT Panel",
)
async def create_admin(
    payload: BotCreateAdminInput,
    db: Session = Depends(get_db),
    _: None = Depends(verify_bot_api_key),
):
    if crud.get_admin_by_username(db, payload.username):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"success": False, "message": "An admin with that username already exists"},
        )

    panel = crud.get_panel_by_name(db, payload.panel)
    if not panel:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": f"No panel named '{payload.panel}'"},
        )
    if panel.panel_type != "marzban":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "Only Marzban panels can be provisioned here"},
        )

    sudo_api = MarzbanAPI(url=panel.url, username=panel.username, password=panel.password)

    # Create in Marzban first. If MIT Panel's row were written first and Marzban
    # then refused, the panel would list an admin that cannot actually serve anyone.
    try:
        marzban_status, detail = await sudo_api.create_admin(
            payload.username, payload.password, payload.telegram_id
        )
    except Exception as e:
        logger.error(f"Marzban admin creation failed for {payload.username}: {e}")
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={"success": False, "message": f"Could not reach Marzban: {e}"},
        )

    if marzban_status != 200:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "success": False,
                "message": f"Marzban refused to create the admin (status {marzban_status}). {detail}",
            },
        )

    # Give the new admin every inbound the panel offers; the superadmin can
    # narrow it afterwards in the panel UI.
    try:
        inbounds = await sudo_api.get_inbounds()
    except Exception:
        inbounds = {}

    expiry_date = None
    if payload.expiry_days:
        expiry_date = datetime.utcnow() + timedelta(days=payload.expiry_days)

    admin_input = AdminInput(
        username=payload.username,
        password=payload.password,
        is_active=True,
        panel=payload.panel,
        inbound_id=None,
        flow=None,
        marzban_inbounds=json.dumps(inbounds) if inbounds else None,
        marzban_password=payload.password,
        traffic=int(payload.traffic_gb * 1024**3),
        update_return_traffic=False,
        delete_return_traffic=False,
        expiry_date=expiry_date,
        telegram_id=payload.telegram_id,
    )
    crud.add_admin(db, admin_input)

    logger.info(f"Bot provisioned new admin {payload.username} on panel {payload.panel}")
    return ResponseModel(
        success=True,
        message="Admin created successfully",
        data={
            "username": payload.username,
            "panel": payload.panel,
            "traffic_gb": payload.traffic_gb,
            "inbounds": inbounds,
            "expiry_date": expiry_date.isoformat() if expiry_date else None,
        },
    )
