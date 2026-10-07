from datetime import datetime
from .engin import Base
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    String,
    Boolean,
    BigInteger,
    Float,
    ForeignKey,
    UniqueConstraint,
)


class Admins(Base):
    __tablename__ = "admins"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    is_active = Column(Boolean, default=True)
    panel = Column(String, nullable=False)
    inbound_id = Column(String, nullable=True)
    marzban_inbounds = Column(String, nullable=True)
    marzban_password = Column(String, nullable=True)
    marzban_all_inbounds = Column(Boolean, default=False, nullable=True)
    traffic = Column(BigInteger, default=0)
    initial_traffic = Column(BigInteger, default=0, nullable=True)
    update_return_traffic = Column(Boolean, default=False)
    delete_return_traffic = Column(Boolean, default=False)
    expiry_date = Column(DateTime, nullable=True)
    inbound_flow = Column(String, nullable=True)
    # Not unique: one person can own several reseller panels (see c7b1d4e88a25).
    telegram_id = Column(BigInteger, nullable=True, index=True)


class Panels(Base):
    __tablename__ = "panels"

    id = Column(Integer, primary_key=True, index=True)
    panel_type = Column(String, nullable=False)
    name = Column(String, unique=True, index=True, nullable=False)
    url = Column(String, nullable=False)
    sub_url = Column(String, nullable=True)
    username = Column(String, nullable=False)
    password = Column(String, nullable=False)
    token = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)


class News(Base):
    __tablename__ = "news"

    id = Column(Integer, primary_key=True, index=True)
    message = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.date)

class SanaeiUsers(Base):
    __tablename__ = "sanaei_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    owner = Column(String, nullable=False)

class GuardUsers(Base):
    __tablename__ = "guard_users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    owner = Column(String, nullable=False)


class MarzbanUsers(Base):
    """Which Marzban usernames each reseller is accounted for owning.

    `admins.traffic` only tells you what is left today; it cannot tell you
    whether a live user was created through the bot (already paid for) or
    straight on the Marzban panel (owed). The usage sync compares this ledger
    against what Marzban actually has, so without a row here a user is debt.
    """

    __tablename__ = "marzban_users"
    __table_args__ = (
        UniqueConstraint("owner", "username", name="uq_marzban_users_owner_username"),
    )

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, nullable=False, index=True)
    owner = Column(String, nullable=False, index=True)
    # Marzban's data_limit for that user: a raised limit means extra quota the
    # reseller has not paid for yet, so the delta is charged, not the whole cap.
    data_limit = Column(BigInteger, default=0, nullable=True)
    # "bot" for users created through MIT Panel, "external" for ones the sync
    # found on Marzban and had to charge for. Informational, for the report.
    source = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=True)


class Servers(Base):
    """A server monitored by the lightweight MIT Panel agent. Not tied to a
    Marzban Panel - any box that runs the agent can be added here."""

    __tablename__ = "servers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    token = Column(String, unique=True, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    sort_order = Column(Integer, default=0, nullable=False)

    last_seen_at = Column(DateTime, nullable=True)
    cpu_percent = Column(Float, nullable=True)
    cpu_cores = Column(Integer, nullable=True)
    ram_used = Column(BigInteger, nullable=True)
    ram_total = Column(BigInteger, nullable=True)
    swap_used = Column(BigInteger, nullable=True)
    swap_total = Column(BigInteger, nullable=True)
    disk_used = Column(BigInteger, nullable=True)
    disk_total = Column(BigInteger, nullable=True)

    reboot_requested = Column(Boolean, default=False)


class TelegramBots(Base):
    """A Nexra sales bot (nexrabot, the Go MirzaBot) this panel manages.

    The panel talks to the bot's management API (/api/v1) with one of two keys:
    owner_key is only ever used for the superadmin, manager_key for the admin
    the bot is assigned to. The bot itself refuses panel (server) changes for
    the manager key, so an admin can run the shop but never touch servers.
    """

    __tablename__ = "telegram_bots"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, unique=True, index=True, nullable=False)
    # Base address of the bot, e.g. https://bot7.example.com (no /api/v1)
    url = Column(String, nullable=False)
    owner_key = Column(String, nullable=False)
    manager_key = Column(String, nullable=False)
    # The admin who runs this bot; null means only the superadmin sees it.
    admin_id = Column(Integer, ForeignKey("admins.id", ondelete="SET NULL"), nullable=True, index=True)
    bot_username = Column(String, nullable=True)
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)
