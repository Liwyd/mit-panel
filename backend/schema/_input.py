from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field


class AdminInput(BaseModel):
    username: str
    password: str
    is_active: bool = True
    panel: str
    inbound_id: Optional[str] = None
    flow: Optional[str] = None
    marzban_inbounds: Optional[str] = None
    marzban_password: Optional[str] = None
    traffic: float = 0.0
    update_return_traffic: bool = False
    delete_return_traffic: bool = False
    expiry_date: datetime | None
    telegram_id: Optional[int] = None


class AdminUpdateInput(BaseModel):
    username: str
    password: Optional[str] = None
    is_active: bool
    panel: str
    inbound_id: Optional[str] = None
    flow: Optional[str] = None
    marzban_inbounds: Optional[str] = None
    marzban_password: Optional[str] = None
    traffic: float
    update_return_traffic: bool = False
    delete_return_traffic: bool = False
    expiry_date: datetime | None
    telegram_id: Optional[int] = None


class PanelInput(BaseModel):
    panel_type: str = "3x-ui"
    name: str
    url: str
    sub_url: str | None = None
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None
    is_active: bool = True


class ClientInput(BaseModel):
    email: str
    id: str  # UUID
    enable: bool = True
    expiry_time: int
    total: float = Field(
        default=0.0, ge=104857600, description="Minimum 0.1 GB (100 MB)"
    )
    sub_id: str
    flow: str = ""


class ClientUpdateInput(BaseModel):
    email: str
    enable: bool = True
    expiry_time: int
    total: float = Field(ge=104857600, description="Minimum 0.1 GB (100 MB)")
    sub_id: str
    flow: str = ""


class NewsInput(BaseModel):
    news: str = Field(
        max_length=250, description="News content must be 250 characters or less"
    )


class BotTopupInput(BaseModel):
    telegram_id: int
    added_gb: float = Field(gt=0)
    # Which of this person's panels to credit. Optional for backwards
    # compatibility: when omitted, the call targets their only panel.
    username: Optional[str] = None


class BotChangePasswordInput(BaseModel):
    telegram_id: int
    new_password: str = Field(min_length=1)
    current_password: str = Field(min_length=1)
    username: Optional[str] = None


class BotGrantInput(BaseModel):
    """Superadmin granting traffic straight to a panel, by username — no
    Telegram link required, so panels nobody has linked yet can still be topped up."""

    username: str
    added_gb: float = Field(gt=0)


class SettingsInput(BaseModel):
    login_title: Optional[str] = None
    telegram_bot_token: Optional[str] = None
    telegram_chat_id: Optional[str] = None
    backup_enabled: Optional[bool] = None
    backup_interval_hours: Optional[int] = None
