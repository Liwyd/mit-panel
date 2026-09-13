from fastapi import APIRouter, Depends, status, UploadFile, File, Form
from fastapi.responses import JSONResponse, FileResponse
from sqlalchemy.orm import Session
import os

from backend.schema.output import (
    ResponseModel,
    AdminOutput,
    PanelOutput,
    ServerOutput,
    ServerCreatedOutput,
)
from backend.schema._input import (
    AdminInput,
    AdminUpdateInput,
    PanelInput,
    NewsInput,
    ServerInput,
    ServerReorderInput,
    SettingsInput,
)
from backend.db import crud
from backend.db.engin import get_db
from backend.services import create_new_panel, update_a_panel
from backend.services.marzban.api import APIService as MarzbanAPI
from backend.utils.logger import logger, get_10_logs
from backend.utils.backup import restore_database
from backend.auth.auth import get_current_superadmin
from backend.utils.system import get_system_info
from backend.utils.marzban_overview import PERIODS, build_marzban_overview
from backend.utils.settings_store import get_settings, update_settings, save_logo
from backend.utils.banners import save_banner, delete_banner, get_banner_path
from backend.utils.telegram import send_backup_to_telegram
from backend.utils.servers import server_status

router = APIRouter(prefix="/superadmin", tags=["superadmin"])


@router.get("/admins", description="Get all admins")
async def get_admins(
    db: Session = Depends(get_db), current_admin: dict = Depends(get_current_superadmin)
):
    all_admins = crud.get_all_admins(db)
    return ResponseModel(
        success=True,
        message="Admins retrieved successfully",
        data=[AdminOutput.from_orm(admin) for admin in all_admins],
    )


@router.post("/admin", description="create a new admin", response_model=ResponseModel)
async def create_admin(
    admin_input: AdminInput,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if crud.get_admin_by_username(db, admin_input.username):
        logger.warning(
            f"Attempt to create admin with duplicate username: {admin_input.username}"
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "message": "Admin with this username already exists",
            },
        )

    crud.add_admin(db, admin_input)
    logger.info(f"New admin created: {admin_input.username}")
    return ResponseModel(
        success=True,
        message="Admin created successfully",
    )


@router.put("/admin/{admin_id}", response_model=ResponseModel)
async def update_admin(
    admin_id: int,
    admin_input: AdminUpdateInput,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if not crud.get_admin_by_username(db, admin_input.username):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Admin not found",
            },
        )
    update_admin = crud.update_admin_values(db, admin_id, admin_input)
    if update_admin:
        return ResponseModel(
            success=True,
            message="Admin updated successfully",
        )


@router.delete("/admin/{admin_id}", response_model=ResponseModel)
async def delete_admin(
    admin_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    remove_admin = crud.remove_admin(db, admin_id)
    if not remove_admin:
        logger.warning(f"Attempt to delete non-existent admin with id: {admin_id}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Admin not found",
            },
        )
    logger.info(f"Admin deleted with id: {admin_id}")
    return ResponseModel(
        success=True,
        message="Admin deleted successfully",
    )


@router.patch("/admin/{admin_id}/status", response_model=ResponseModel)
async def toggle_admin_status(
    admin_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    status_changed = crud.change_admin_status(db, admin_id)
    if not status_changed:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Admin not found",
            },
        )
    return ResponseModel(
        success=True,
        message="Admin status changed successfully",
    )


@router.get("/panels", description="Get all panels")
async def get_panels(
    db: Session = Depends(get_db), current_admin: dict = Depends(get_current_superadmin)
):
    all_panels = crud.get_all_panels(db)
    return ResponseModel(
        success=True,
        message="Panels retrieved successfully",
        data=[PanelOutput.from_orm(panel) for panel in all_panels],
    )


@router.post("/panel", description="add a new panel", response_model=ResponseModel)
async def create_panel(
    panel_input: PanelInput,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if crud.get_panel_by_name(db, panel_input.name):
        logger.warning(
            f"Attempt to create panel with duplicate name: {panel_input.name}"
        )
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "success": False,
                "message": "Panel with this name already exists",
            },
        )

    connection = await create_new_panel(db, panel_input)
    if not connection:
        logger.error(
            f"Failed to connect to panel: {panel_input.name} at {panel_input.url}"
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "Failed to connect to the panel with provided credentials",
            },
        )

    crud.add_panel(db, panel_input)
    logger.info(f"New panel created: {panel_input.name}")
    return ResponseModel(
        success=True,
        message="Panel created successfully",
    )


@router.put("/panel/{panel_id}", response_model=ResponseModel)
async def update_panel(
    panel_id: int,
    panel_input: PanelInput,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if not crud.get_panel_by_id(db, panel_id):
        logger.warning(f"Attempt to update non-existent panel with id: {panel_id}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Panel not found",
            },
        )
    connection = await update_a_panel(db, panel_input)
    if not connection:
        logger.error(
            f"Failed to connect to panel: {panel_input.name} at {panel_input.url} during update"
        )
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "Failed to connect to the panel with provided credentials",
            },
        )

    crud.update_panel_values(db, panel_id, panel_input)
    logger.info(f"Panel updated with id: {panel_id} ({panel_input.name})")
    return ResponseModel(
        success=True,
        message="Panel updated successfully",
    )


@router.delete("/panel/{panel_id}", response_model=ResponseModel)
async def delete_panel(
    panel_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    remove_panel = crud.remove_panel(db, panel_id)
    if not remove_panel:
        logger.warning(f"Attempt to delete non-existent panel with id: {panel_id}")
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Panel not found",
            },
        )
    logger.info(f"Panel deleted with id: {panel_id}")
    return ResponseModel(
        success=True,
        message="Panel deleted successfully",
    )


@router.patch("/panel/{panel_id}/status", response_model=ResponseModel)
async def toggle_panel_status(
    panel_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    status_changed = crud.change_panel_status(db, panel_id)
    if not status_changed:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Panel not found",
            },
        )
    return ResponseModel(
        success=True,
        message="Panel status changed successfully",
    )


@router.get("/panel/{panel_name}/inbounds")
async def get_panel_inbounds(
    panel_name: str,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    """Get available inbounds for a Marzban panel"""
    panel = crud.get_panel_by_name(db, panel_name)
    if not panel:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Panel not found",
            },
        )

    if panel.panel_type != "marzban":
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "Only Marzban panels support inbound selection",
            },
        )

    try:
        api_service = MarzbanAPI(
            url=panel.url,
            username=panel.username,
            password=panel.password,
        )
        inbounds = await api_service.get_inbounds()
        return ResponseModel(
            success=True, message="Inbounds retrieved successfully", data=inbounds
        )
    except Exception as e:
        logger.error(f"Failed to fetch inbounds from panel {panel_name}: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": f"Failed to fetch inbounds: {str(e)}",
            },
        )


@router.get("/backup", description="Download database backup")
async def download_backup(admin: dict = Depends(get_current_superadmin)):
    """Download the current database as a backup file"""
    db_path = "/app/data/mitpanel.db"
    if not os.path.exists(db_path):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "success": False,
                "message": "Database file not found",
            },
        )

    return FileResponse(
        path=db_path,
        filename="mitpanel.db",
        media_type="application/octet-stream",
    )


@router.post(
    "/restore",
    description="Restore database from uploaded file",
    response_model=ResponseModel,
)
async def restore_backup(
    file: UploadFile = File(...), admin: dict = Depends(get_current_superadmin)
):
    """Restore database from an uploaded backup file"""
    if not file.filename.endswith(".db"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "Only .db files are allowed",
            },
        )

    db_path = "/app/data/mitpanel.db"
    try:
        restore_database(db_path, file)
        return ResponseModel(
            success=True,
            message="Database restored successfully. Please restart the container to apply changes.",
        )

    except Exception as e:
        logger.error(f"Restore failed: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": f"Failed to restore database: {str(e)}",
            },
        )


@router.get("/logs", description="Get application logs")
async def get_logs(admin: dict = Depends(get_current_superadmin)):
    """Get the last 10 application logs"""
    try:
        logs = get_10_logs()
        return ResponseModel(
            success=True,
            message="Logs retrieved successfully",
            data=logs,
        )
    except Exception as e:
        logger.error(f"Failed to retrieve logs: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": f"Failed to retrieve logs: {str(e)}",
            },
        )


@router.get("/news", description="Get news")
async def get_news(
    db: Session = Depends(get_db), admin: dict = Depends(get_current_superadmin)
):
    """Get the news"""
    try:
        news = crud.get_news(db)
        return ResponseModel(
            success=True,
            message="News retrieved successfully",
            data=list(
                map(
                    lambda x: {
                        "id": x.id,
                        "message": x.message,
                        "created_at": x.created_at,
                        "has_banner": get_banner_path(x.id) is not None,
                    },
                    news,
                )
            ),
        )
    except Exception as e:
        logger.error(f"Failed to retrieve news: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": f"Failed to retrieve news: {str(e)}",
            },
        )


@router.post("/news", description="Add news", response_model=ResponseModel)
async def add_news(
    message: str | None = Form(None, max_length=250),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    """Add news: a message, a banner image, or both - at least one is required."""
    text = (message or "").strip() or None

    image_bytes: bytes | None = None
    if image is not None and image.filename:
        image_bytes = await image.read()
        if image_bytes and not (image.content_type or "").startswith("image/"):
            return JSONResponse(
                status_code=status.HTTP_400_BAD_REQUEST,
                content={"success": False, "message": "Only image files are allowed"},
            )

    if not text and not image_bytes:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "message": "Add a message, a banner image, or both",
            },
        )

    try:
        news = crud.add_news(db, text)
        if image_bytes:
            save_banner(news.id, image_bytes)
        return ResponseModel(
            success=True,
            message="News added successfully",
        )
    except Exception as e:
        logger.error(f"Failed to add news: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": f"Failed to add news: {str(e)}",
            },
        )


@router.delete(
    "/news/{news_id}", description="Delete news", response_model=ResponseModel
)
async def delete_news(
    news_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    """Delete news by ID"""
    try:
        news = db.query(crud.News).filter(crud.News.id == news_id).first()
        if not news:
            return JSONResponse(
                status_code=status.HTTP_404_NOT_FOUND,
                content={
                    "success": False,
                    "message": "News not found",
                },
            )
        db.delete(news)
        db.commit()
        delete_banner(news_id)
        return ResponseModel(
            success=True,
            message="News deleted successfully",
        )
    except Exception as e:
        logger.error(f"Failed to delete news: {str(e)}")
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={
                "success": False,
                "message": f"Failed to delete news: {str(e)}",
            },
        )


@router.get("/system", description="Get system information")
async def get_system_info_endpoint(
    db: Session = Depends(get_db), current_admin: dict = Depends(get_current_superadmin)
):

    system_info = get_system_info()
    return JSONResponse(content={"success": True, "data": system_info})


@router.get("/marzban/overview", description="Aggregated Marzban stats for the dashboard")
async def get_marzban_overview(
    period: str = "1d",
    refresh: bool = False,
    include_admins: bool = False,
    db: Session = Depends(get_db),
    current_admin: dict = Depends(get_current_superadmin),
):
    """User counts, lifetime traffic, host CPU/RAM and per-node usage for the
    first active Marzban panel. Failures degrade to an empty payload rather
    than an error so one unreachable panel never blanks the dashboard."""
    if period not in PERIODS:
        period = "1d"

    panel = next(
        (
            p
            for p in crud.get_all_panels(db)
            if p.panel_type == "marzban" and p.is_active
        ),
        None,
    )

    if not panel:
        return ResponseModel(
            success=True,
            message="No active Marzban panel configured",
            data=None,
        )

    try:
        api_service = MarzbanAPI(
            url=panel.url,
            username=panel.username,
            password=panel.password,
        )
        data = await build_marzban_overview(api_service, panel.name, period, force=refresh)

        if include_admins:
            try:
                marzban_admins = await api_service.get_admins()
                marzban_usernames = {a["username"] for a in marzban_admins if a.get("username")}
                mit_usernames = {a.username for a in crud.get_all_admins(db)}
                data["admins"] = {
                    "mit": len(mit_usernames),
                    "marzban_only": len(marzban_usernames - mit_usernames),
                }
            except Exception as e:
                logger.warning(f"Failed to compute admin ratio from {panel.name}: {str(e)}")
                data["admins"] = None

        return ResponseModel(
            success=True,
            message="Marzban overview retrieved successfully",
            data=data,
        )
    except Exception as e:
        logger.error(f"Failed to build Marzban overview from {panel.name}: {str(e)}")
        return ResponseModel(
            success=True,
            message=f"Marzban is unreachable: {str(e)}",
            data=None,
        )


def _server_to_output(server) -> ServerOutput:
    return ServerOutput(
        id=server.id,
        name=server.name,
        status=server_status(server),
        last_seen_at=server.last_seen_at,
        cpu_percent=server.cpu_percent,
        cpu_cores=server.cpu_cores,
        ram_used=server.ram_used,
        ram_total=server.ram_total,
        swap_used=server.swap_used,
        swap_total=server.swap_total,
        disk_used=server.disk_used,
        disk_total=server.disk_total,
    )


@router.get("/servers", description="Get all monitored servers")
async def get_servers(
    db: Session = Depends(get_db), current_admin: dict = Depends(get_current_superadmin)
):
    servers = crud.get_all_servers(db)
    return ResponseModel(
        success=True,
        message="Servers retrieved successfully",
        data=[_server_to_output(s) for s in servers],
    )


@router.post("/servers", description="Add a server to monitor")
async def create_server(
    server_input: ServerInput,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if any(s.name == server_input.name for s in crud.get_all_servers(db)):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={"success": False, "message": "A server with this name already exists"},
        )

    server = crud.add_server(db, server_input.name)
    logger.info(f"New monitored server added: {server.name}")
    return ResponseModel(
        success=True,
        message="Server added successfully",
        data=ServerCreatedOutput(id=server.id, name=server.name, token=server.token),
    )


@router.put("/servers/reorder", description="Set the display order of monitored servers")
async def reorder_servers(
    reorder_input: ServerReorderInput,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if not crud.reorder_servers(db, reorder_input.ordered_ids):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "ordered_ids must list every existing server exactly once"},
        )
    return ResponseModel(success=True, message="Server order updated")


@router.put("/servers/{server_id}", description="Rename a monitored server")
async def rename_server(
    server_id: int,
    server_input: ServerInput,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if not crud.rename_server(db, server_id, server_input.name):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "Server not found"},
        )
    return ResponseModel(success=True, message="Server renamed successfully")


@router.delete("/servers/{server_id}", description="Stop monitoring a server")
async def delete_server(
    server_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if not crud.remove_server(db, server_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "Server not found"},
        )
    return ResponseModel(success=True, message="Server removed successfully")


@router.post("/servers/{server_id}/reboot", description="Queue a reboot for a server")
async def reboot_server(
    server_id: int,
    db: Session = Depends(get_db),
    admin: dict = Depends(get_current_superadmin),
):
    if not crud.request_server_reboot(db, server_id):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={"success": False, "message": "Server not found"},
        )
    logger.info(f"Reboot requested for server #{server_id} by {admin.get('username')}")
    return ResponseModel(
        success=True,
        message="Reboot queued - it will run on the server's next check-in",
    )


@router.get("/settings", description="Get panel settings")
async def get_panel_settings(admin: dict = Depends(get_current_superadmin)):
    return ResponseModel(
        success=True,
        message="Settings retrieved successfully",
        data=get_settings(),
    )


@router.put("/settings", description="Update panel settings", response_model=ResponseModel)
async def update_panel_settings(
    payload: SettingsInput,
    admin: dict = Depends(get_current_superadmin),
):
    data = update_settings(payload.model_dump(exclude_unset=True))
    logger.info("Panel settings updated")
    return ResponseModel(
        success=True,
        message="Settings updated successfully",
        data=data,
    )


@router.post(
    "/settings/logo", description="Upload login logo", response_model=ResponseModel
)
async def upload_login_logo(
    file: UploadFile = File(...),
    admin: dict = Depends(get_current_superadmin),
):
    content = await file.read()
    if not content or not (file.content_type or "").startswith("image/"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={"success": False, "message": "Only image files are allowed"},
        )
    save_logo(content)
    logger.info("Login logo updated")
    return ResponseModel(success=True, message="Logo updated successfully")


@router.post(
    "/settings/telegram/test",
    description="Send a test backup to Telegram",
    response_model=ResponseModel,
)
async def test_telegram_backup(admin: dict = Depends(get_current_superadmin)):
    ok, message = await send_backup_to_telegram()
    if ok:
        return ResponseModel(success=True, message=message)
    return JSONResponse(
        status_code=status.HTTP_400_BAD_REQUEST,
        content={"success": False, "message": message},
    )


@router.get("/settings/bot", description="Get top-up bot settings")
async def get_bot_settings(admin: dict = Depends(get_current_superadmin)):
    settings = get_settings()
    bot_data = {
        "bot_enabled": settings.get("bot_enabled", False),
        "bot_token": settings.get("bot_token", ""),
        "bot_superadmin_ids": settings.get("bot_superadmin_ids", ""),
        "bot_media_dir": settings.get("bot_media_dir", "data/bot_media"),
        "bot_min_gb": settings.get("bot_min_gb", 200.0),
        "bot_max_gb": settings.get("bot_max_gb", 10000.0),
    }
    return ResponseModel(
        success=True,
        message="Bot settings retrieved successfully",
        data=bot_data,
    )


@router.put("/settings/bot", description="Update top-up bot settings and restart bot", response_model=ResponseModel)
async def update_bot_settings(
    payload: SettingsInput,
    admin: dict = Depends(get_current_superadmin),
):
    patch = payload.model_dump(exclude_unset=True)
    allowed = {"bot_enabled", "bot_token", "bot_superadmin_ids", "bot_media_dir", "bot_min_gb", "bot_max_gb"}
    bot_patch = {k: v for k, v in patch.items() if k in allowed}

    if bot_patch:
        update_settings(bot_patch)

    # Sync to .env file so the bot picks up changes on restart
    env_path = os.path.join(os.path.dirname(__file__), "..", "..", "..", ".env")
    env_path = os.path.normpath(env_path)
    if os.path.exists(env_path):
        with open(env_path, "r") as f:
            lines = f.readlines()

        env_map = {}
        for i, line in enumerate(lines):
            line_stripped = line.strip()
            if line_stripped and not line_stripped.startswith("#") and "=" in line_stripped:
                key = line_stripped.split("=", 1)[0]
                env_map[key] = i

        env_updates = {}
        if "bot_token" in bot_patch:
            env_updates["BOT_TOKEN"] = bot_patch["bot_token"]
        if "bot_superadmin_ids" in bot_patch:
            env_updates["BOT_SUPERADMIN_IDS"] = bot_patch["bot_superadmin_ids"]
        if "bot_media_dir" in bot_patch:
            env_updates["BOT_MEDIA_DIR"] = bot_patch["bot_media_dir"]
        if "bot_min_gb" in bot_patch:
            env_updates["BOT_MIN_GB"] = str(bot_patch["bot_min_gb"])
        if "bot_max_gb" in bot_patch:
            env_updates["BOT_MAX_GB"] = str(bot_patch["bot_max_gb"])

        for key, value in env_updates.items():
            if key in env_map:
                lines[env_map[key]] = f"{key}={value}\n"
            else:
                lines.append(f"{key}={value}\n")

        with open(env_path, "w") as f:
            f.writelines(lines)

    logger.info("Bot settings updated")
    return ResponseModel(
        success=True,
        message="Bot settings updated. Restart the panel to apply changes.",
        data=get_settings(),
    )
