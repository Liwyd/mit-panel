"""Adapter that wraps the panel's CRUD/service layer for the bot.

All functions return dicts matching the expected interface
so the bot's existing code requires minimal changes.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timedelta

from backend.db.engin import sessionLocal
from backend.db import crud
from backend.db.model import Admins

logger = logging.getLogger(__name__)


class PanelClientError(Exception):
    pass


def _session():
    return sessionLocal()


def _admin_to_dict(a: Admins) -> dict:
    """Serialize an Admins ORM object to the dict format the bot expects."""
    return {
        "username": a.username,
        "telegram_id": a.telegram_id,
        "traffic": a.traffic or 0,
        "initial_traffic": a.initial_traffic or 0,
        "is_active": a.is_active,
        "panel": a.panel,
        "marzban_password": a.marzban_password,
    }


async def get_admins(telegram_id: int) -> list[dict]:
    """Every panel this Telegram account owns — empty list if none."""
    with _session() as db:
        admins = crud.get_admins_by_telegram_id(db, telegram_id)
        if not admins:
            return []
        return [_admin_to_dict(a) for a in admins]


async def get_admin(telegram_id: int) -> dict | None:
    """Their single panel, or None."""
    admins = await get_admins(telegram_id)
    return admins[0] if len(admins) == 1 else None


async def list_all_admins() -> list[dict]:
    """All admins across all panels."""
    with _session() as db:
        admins = crud.get_all_admins(db)
        return [_admin_to_dict(a) for a in admins]


async def topup(telegram_id: int, added_gb: float, username: str | None = None) -> dict:
    """Credit traffic to a panel and return the result dict."""
    added_bytes = int(added_gb * 1024**3)
    with _session() as db:
        if username:
            admin = crud.get_owned_admin(db, telegram_id, username)
            if not admin:
                raise PanelClientError("No panel linked to this Telegram account")
        else:
            admins = crud.get_admins_by_telegram_id(db, telegram_id)
            if not admins:
                raise PanelClientError("No admin is linked to this Telegram account")
            if len(admins) > 1:
                raise PanelClientError("Multiple panels found; specify username")
            admin = admins[0]

        crud.grant_admin_traffic(db, admin, added_bytes)
        return {
            "username": admin.username,
            "telegram_id": admin.telegram_id,
            "new_traffic_bytes": admin.traffic,
            "new_initial_traffic_bytes": admin.initial_traffic,
        }


async def create_admin(
    username: str,
    password: str,
    panel: str,
    traffic_gb: float,
    expiry_days: int | None,
    telegram_id: int | None,
) -> dict:
    """Create a new admin in Marzban and MIT Panel."""
    with _session() as db:
        if crud.get_admin_by_username(db, username):
            raise PanelClientError("An admin with that username already exists")

        panel_obj = crud.get_panel_by_name(db, panel)
        if not panel_obj:
            raise PanelClientError(f"No panel named '{panel}'")
        if panel_obj.panel_type != "marzban":
            raise PanelClientError("Only Marzban panels can be provisioned here")

        from backend.services.marzban.api import APIService as MarzbanAPI

        sudo_api = MarzbanAPI(
            url=panel_obj.url, username=panel_obj.username, password=panel_obj.password
        )

        try:
            marzban_status, detail = await sudo_api.create_admin(
                username, password, telegram_id
            )
        except Exception as e:
            raise PanelClientError(f"Could not reach Marzban: {e}")

        if marzban_status != 200:
            raise PanelClientError(
                f"Marzban refused to create the admin (status {marzban_status}). {detail}"
            )

        try:
            inbounds = await sudo_api.get_inbounds()
        except Exception:
            inbounds = {}

        expiry_date = None
        if expiry_days:
            expiry_date = datetime.utcnow() + timedelta(days=expiry_days)

        from backend.schema._input import AdminInput

        admin_input = AdminInput(
            username=username,
            password=password,
            is_active=True,
            panel=panel,
            inbound_id=None,
            flow=None,
            marzban_inbounds=json.dumps(inbounds) if inbounds else None,
            marzban_password=password,
            traffic=int(traffic_gb * 1024**3),
            update_return_traffic=True,
            delete_return_traffic=True,
            expiry_date=expiry_date,
            telegram_id=telegram_id,
        )
        crud.add_admin(db, admin_input)

        return {
            "username": username,
            "panel": panel,
            "traffic_gb": traffic_gb,
            "inbounds": inbounds,
            "expiry_date": expiry_date.isoformat() if expiry_date else None,
        }


async def list_panels() -> list[str]:
    """Names of Marzban panels a new reseller can be created on."""
    with _session() as db:
        panels = crud.get_all_panels(db)
        return sorted(p.name for p in panels if p.panel_type == "marzban")


async def create_panel(name: str, url: str, username: str, password: str) -> dict:
    """Test connection and save a new Marzban panel."""
    with _session() as db:
        if crud.get_panel_by_name(db, name):
            raise PanelClientError(f"A panel named '{name}' already exists")

        from backend.services.marzban.api import APIService as MarzbanAPI
        api = MarzbanAPI(url=url, username=username, password=password)
        ok = await api.test_connection()
        if not ok:
            raise PanelClientError(
                "Could not connect to Marzban. Check URL and credentials."
            )

        from backend.schema._input import PanelInput
        crud.add_panel(
            db,
            PanelInput(
                panel_type="marzban",
                name=name,
                url=url,
                username=username,
                password=password,
                is_active=True,
            ),
        )
        return {"name": name, "url": url}


async def grant(username: str, added_gb: float) -> dict:
    """Superadmin direct traffic grant."""
    added_bytes = int(added_gb * 1024**3)
    with _session() as db:
        admin = crud.get_admin_by_username(db, username)
        if not admin:
            raise PanelClientError("No admin with that username")
        crud.grant_admin_traffic(db, admin, added_bytes)
        return {
            "username": admin.username,
            "telegram_id": admin.telegram_id,
            "new_traffic_bytes": admin.traffic,
            "new_initial_traffic_bytes": admin.initial_traffic,
        }


async def change_password(
    telegram_id: int,
    current_password: str,
    new_password: str,
    username: str | None = None,
) -> dict:
    """Change a panel's Marzban password with current-password verification."""
    with _session() as db:
        if username:
            admin = crud.get_owned_admin(db, telegram_id, username)
            if not admin:
                raise PanelClientError("No panel linked to this Telegram account")
        else:
            admins = crud.get_admins_by_telegram_id(db, telegram_id)
            if not admins:
                raise PanelClientError("No admin is linked to this Telegram account")
            if len(admins) > 1:
                raise PanelClientError("Multiple panels found; specify username")
            admin = admins[0]

        panel_obj = crud.get_panel_by_name(db, admin.panel)
        if not panel_obj or panel_obj.panel_type != "marzban":
            raise PanelClientError("This admin's panel is not a Marzban panel")

        if admin.username == panel_obj.username:
            raise PanelClientError(
                "This is the panel's own service account; its password can't be changed"
            )

        from backend.services.marzban.api import APIService as MarzbanAPI

        # Verify current password
        verify_api = MarzbanAPI(
            url=panel_obj.url, username=admin.username, password=current_password
        )
        try:
            current_ok = await verify_api.test_connection()
        except Exception as e:
            raise PanelClientError(f"Could not reach Marzban: {e}")

        if not current_ok:
            raise PanelClientError("Current password is incorrect")

        # Change password via sudo
        sudo_api = MarzbanAPI(
            url=panel_obj.url, username=panel_obj.username, password=panel_obj.password
        )
        try:
            marzban_status = await sudo_api.update_admin_password(
                admin.username, new_password
            )
        except Exception as e:
            raise PanelClientError(f"Marzban password change failed: {e}")

        if marzban_status != 200:
            hints = {
                401: "MIT Panel's stored Marzban credentials are wrong or expired.",
                403: "This panel's stored Marzban credentials are not a sudo admin.",
                404: f"Marzban has no admin named '{admin.username}'.",
                422: "Marzban rejected the request body.",
            }
            detail = hints.get(marzban_status, "Unexpected response from Marzban.")
            raise PanelClientError(
                f"Marzban rejected the password change (status {marzban_status}). {detail}"
            )

        crud.update_marzban_password(db, admin, new_password)
        return {"telegram_id": admin.telegram_id, "username": admin.username}


async def sync_telegram_ids() -> dict:
    """Pull Telegram IDs from Marzban into MIT Panel."""
    updated: list[dict] = []
    skipped: list[str] = []

    with _session() as db:
        marzban_panels = [
            p for p in crud.get_all_panels(db) if p.panel_type == "marzban"
        ]
        for panel in marzban_panels:
            from backend.services.marzban.api import APIService as MarzbanAPI

            sudo_api = MarzbanAPI(
                url=panel.url, username=panel.username, password=panel.password
            )
            try:
                marzban_admins = await sudo_api.get_admins()
            except Exception as e:
                logger.error(f"Failed to fetch admins from Marzban panel {panel.name}: {e}")
                continue

            marzban_by_username = {a.get("username"): a for a in marzban_admins}
            panel_admins = [a for a in crud.get_all_admins(db) if a.panel == panel.name]

            for admin in panel_admins:
                if admin.telegram_id:
                    continue
                m = marzban_by_username.get(admin.username)
                marzban_tid = m.get("telegram_id") if m else None
                if not marzban_tid:
                    continue

                admin.telegram_id = marzban_tid
                try:
                    db.commit()
                    updated.append({"username": admin.username, "telegram_id": marzban_tid})
                except Exception:
                    db.rollback()
                    skipped.append(admin.username)

    return {"updated": updated, "skipped_conflicts": skipped}


async def create_admin_for_shop(
    username: str,
    password: str,
    panel: str,
    traffic_gb: float,
    telegram_id: int,
) -> dict:
    """Create a new admin for a shop purchase — return traffic enabled, no expiry."""
    with _session() as db:
        if crud.get_admin_by_username(db, username):
            raise PanelClientError("An admin with that username already exists")

        panel_obj = crud.get_panel_by_name(db, panel)
        if not panel_obj:
            raise PanelClientError(f"No panel named '{panel}'")
        if panel_obj.panel_type != "marzban":
            raise PanelClientError("Only Marzban panels can be provisioned here")

        from backend.services.marzban.api import APIService as MarzbanAPI

        sudo_api = MarzbanAPI(
            url=panel_obj.url, username=panel_obj.username, password=panel_obj.password
        )

        try:
            marzban_status, detail = await sudo_api.create_admin(
                username, password, telegram_id
            )
        except Exception as e:
            raise PanelClientError(f"Could not reach Marzban: {e}")

        if marzban_status != 200:
            raise PanelClientError(
                f"Marzban refused to create the admin (status {marzban_status}). {detail}"
            )

        try:
            inbounds = await sudo_api.get_inbounds()
        except Exception:
            inbounds = {}

        from backend.schema._input import AdminInput

        admin_input = AdminInput(
            username=username,
            password=password,
            is_active=True,
            panel=panel,
            inbound_id=None,
            flow=None,
            marzban_inbounds=json.dumps(inbounds) if inbounds else None,
            marzban_password=password,
            traffic=int(traffic_gb * 1024**3),
            update_return_traffic=True,
            delete_return_traffic=True,
            expiry_date=None,
            telegram_id=telegram_id,
        )
        crud.add_admin(db, admin_input)

        return {
            "username": username,
            "password": password,
            "panel": panel,
            "traffic_gb": traffic_gb,
        }


async def topup_by_username(username: str, added_gb: float) -> dict:
    """Credit traffic to an admin by Marzban username (used for referral bonus)."""
    added_bytes = int(added_gb * 1024**3)
    with _session() as db:
        admin = crud.get_admin_by_username(db, username)
        if not admin:
            raise PanelClientError("No admin with that username")
        crud.grant_admin_traffic(db, admin, added_bytes)
        return {
            "username": admin.username,
            "telegram_id": admin.telegram_id,
            "new_traffic_bytes": admin.traffic,
            "new_initial_traffic_bytes": admin.initial_traffic,
        }


async def delete_admin_by_username(username: str) -> dict:
    """Delete an admin from MIT Panel DB only.

    Marzban deletion must be done manually — returns a flag indicating this.
    """
    with _session() as db:
        admin = crud.get_admin_by_username(db, username)
        if not admin:
            raise PanelClientError("No admin with that username")
        telegram_id = admin.telegram_id
        panel_name = admin.panel
        crud.remove_admin(db, admin.id)
        return {
            "username": username,
            "telegram_id": telegram_id,
            "panel": panel_name,
            "needs_marzban_cleanup": True,
        }
