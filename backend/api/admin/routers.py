from fastapi import APIRouter, Depends, status
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session


from backend.db.engin import get_db
from backend.auth import get_current_admin
from backend.schema._input import ClientInput, ClientUpdateInput
from backend.services import (
    add_new_user,
    update_a_user,
    delete_a_user,
    get_all_users_from_panel,
    reset_a_user_usage,
)
from backend.db import crud
from backend.services.limit_handler import AdminLimiter
from backend.services.marzban.api import APIService, MarzbanUserUnavailable
from backend.schema.output import ResponseModel
from backend.utils import analytics
from backend.utils.logger import logger
from backend.utils.settings_store import get_node_names

router = APIRouter(prefix="/admin", tags=["Admin"])


@router.post("/user/{username}/revoke-subscription")
async def revoke_subscription(
    username: str,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin.get("role") != "admin":
        return JSONResponse(status_code=403, content={"success": False, "message": "Not authorized"})
    admin = crud.get_admin_by_username(db, current_admin["username"])
    if not admin or not AdminLimiter(db, current_admin["username"]).admin_is_active():
        return JSONResponse(status_code=403, content={"success": False, "message": "Admin account is inactive"})
    panel = crud.get_panel_by_name(db, admin.panel)
    if not panel or panel.panel_type != "marzban":
        return JSONResponse(status_code=400, content={"success": False, "message": "Subscription revocation unavailable"})
    try:
        user = await APIService(
            panel.url, admin.username, admin.marzban_password or ""
        ).revoke_subscription(username)
    except MarzbanUserUnavailable:
        return JSONResponse(status_code=404, content={"success": False, "message": "User unavailable"})
    except Exception:
        logger.exception("Subscription revoke failed for admin %s user %s", admin.username, username)
        return JSONResponse(status_code=502, content={"success": False, "message": "Could not confirm revocation; refresh before retrying"})
    logger.info("Subscription revoked by admin %s for user %s", admin.username, username)
    return {"success": True, "message": "Subscription revoked", "data": {"subscription_url": user["subscription_url"]}}


@router.get("/user", description="Get all users")
async def get_all_users(
    db: Session = Depends(get_db), current_admin: dict = Depends(get_current_admin)
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await get_all_users_from_panel(
        admin_username=current_admin["username"], db=db
    )
    return result


@router.post("/user", description="Add a new user")
async def add_user(
    user_input: ClientInput,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await add_new_user(
        admin_username=current_admin["username"], user_input=user_input, db=db
    )
    return result


@router.put("/user/{uuid}", description="Update an existing user")
async def update_user(
    uuid: str,
    user_input: ClientUpdateInput,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await update_a_user(
        admin_username=current_admin["username"],
        uuid=uuid,
        user_input=user_input,
        db=db,
    )
    return result


@router.put("/user/{email}/reset", description="Reset user usage statistics")
async def reset_user_usage(
    email: str,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await reset_a_user_usage(
        admin_username=current_admin["username"], email=email, db=db
    )
    return result


@router.delete("/user/{uuid}", description="Delete a user")
async def delete_user(
    uuid: str,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin["role"] != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )

    result = await delete_a_user(
        admin_username=current_admin["username"], uuid=uuid, db=db
    )
    return result


@router.get("/analytics", description="Usage, sales forecast and node ranking for the Analytics page")
async def get_analytics(
    period: str = "1d",
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_admin),
):
    if current_admin.get("role") != "admin":
        return JSONResponse(
            status_code=status.HTTP_403_FORBIDDEN,
            content={"detail": "Not authorized to access this resource."},
        )
    admin = crud.get_admin_by_username(db, current_admin["username"])
    if admin is None:
        return JSONResponse(status_code=status.HTTP_404_NOT_FOUND, content={"detail": "Admin not found."})
    if period not in analytics.NODE_PERIODS:
        period = "1d"

    data = analytics.build_admin_analytics(db, admin)

    # The node ranking is the one part read from Marzban itself; when it
    # can't be read, the rest of the page still loads.
    data["nodes"] = {"period": period, "items": None, "total": 0}
    panel = crud.get_panel_by_name(db, admin.panel)
    if panel and panel.panel_type == "marzban" and panel.is_active:
        try:
            api_service = APIService(url=panel.url, username=panel.username, password=panel.password)
            items = await analytics.admin_node_usage(api_service, admin, period)
            items = analytics.apply_node_names(items, get_node_names().get(str(panel.id), {}))
            data["nodes"] = {"period": period, "items": items, "total": sum(n["used"] for n in items)}
        except Exception as e:
            logger.warning(f"Analytics: could not read node usage of {admin.username}: {e}")

    return ResponseModel(success=True, message="Analytics retrieved successfully", data=data)
