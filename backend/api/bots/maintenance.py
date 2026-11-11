"""Superadmin controls for the local hosting-invoice scheduler."""

import asyncio

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, StrictBool, Field

from backend.auth.auth import get_current_admin
from backend.bot import maintenance
from backend.bot.service import is_running
from backend.schema.output import ResponseModel

router = APIRouter(prefix="/sales-bots/maintenance", tags=["Bot maintenance"])


class PriceInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    eur_price: str = Field(max_length=32)


class EnrollmentInput(BaseModel):
    model_config = ConfigDict(extra="forbid")
    enabled: StrictBool


def _denied(user):
    if user.get("role") != "superadmin":
        return JSONResponse(
            status_code=403, content={"success": False, "message": "Access denied"}
        )
    return None


@router.get("")
async def overview(user: dict = Depends(get_current_admin)):
    if denied := _denied(user):
        return denied
    data = await asyncio.to_thread(maintenance.list_billing)
    data["running"] = is_running()
    return ResponseModel(success=True, message="Bot maintenance billing", data=data)


@router.put("/price")
async def change_price(payload: PriceInput, user: dict = Depends(get_current_admin)):
    if denied := _denied(user):
        return denied
    try:
        price = await asyncio.to_thread(maintenance.set_price, payload.eur_price)
    except ValueError as exc:
        return JSONResponse(
            status_code=400, content={"success": False, "message": str(exc)}
        )
    return ResponseModel(
        success=True, message="Monthly price saved", data={"eur_price": price}
    )


@router.put("/{bot_id}")
async def enroll(
    bot_id: int, payload: EnrollmentInput, user: dict = Depends(get_current_admin)
):
    if denied := _denied(user):
        return denied
    if payload.enabled and not is_running():
        return JSONResponse(
            status_code=409,
            content={
                "success": False,
                "message": "The Telegram invoicing bot must be running before enabling billing.",
            },
        )
    try:
        await asyncio.to_thread(maintenance.set_enabled, bot_id, payload.enabled)
    except ValueError as exc:
        return JSONResponse(
            status_code=400, content={"success": False, "message": str(exc)}
        )
    return ResponseModel(success=True, message="Maintenance billing saved")
