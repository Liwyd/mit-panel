"""Cut off a late-paying sub-admin's users, and bring exactly them back.

Suspending disables every *active* user the sub-admin owns on their panel and
records each one in the bot database first. Unsuspending re-enables only the
recorded users, so users the sub-admin had disabled themselves stay disabled.
Only the status changes: volume, expiry and the traffic accounting are never
touched, so nothing is charged or refunded either way.

Marzban and 3x-ui panels are supported. The user list is read in full before
anything is changed, and a read that might be partial aborts the whole run
rather than suspending half a reseller.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Awaitable, Callable

from backend.bot import db
from backend.db import crud, engin
from backend.services.marzban import APIService as MarzbanAPI
from backend.services.marzban.api import MarzbanAPIError
from backend.services.sanaei import APIService as SanaeiAPI
from backend.utils.logger import logger

SUPPORTED = {"marzban", "3x-ui"}
# Panels are asked a few users at a time: fast enough for a few thousand
# users, gentle enough not to look like an attack on the panel.
CONCURRENCY = 5

Progress = Callable[[int, int], Awaitable[None]]


class SuspendError(Exception):
    """Nothing was changed; the message is shown to the superadmin."""


@dataclass
class Target:
    username: str
    telegram_id: int | None
    panel_type: str
    panel_name: str
    panel_url: str
    panel_user: str
    panel_pass: str
    panel_token: str
    admin_password: str


@dataclass
class Result:
    done: int = 0
    failed: int = 0
    skipped: int = 0
    total: int = 0


def _name_key(name: str | None) -> str:
    return (name or "").strip().lower()


def load_target(admin_username: str) -> Target:
    with engin.sessionLocal() as session:
        admin = crud.get_admin_by_username(session, admin_username)
        if admin is None:
            raise SuspendError("این ساب‌ادمین پیدا نشد")
        panel = crud.get_panel_by_name(session, admin.panel) if admin.panel else None
        if panel is None:
            raise SuspendError("پنل این ساب‌ادمین پیدا نشد")
        if panel.panel_type not in SUPPORTED:
            raise SuspendError(f"قطع کاربران برای پنل نوع {panel.panel_type} پشتیبانی نمی‌شود")
        return Target(
            username=admin.username,
            telegram_id=admin.telegram_id,
            panel_type=panel.panel_type,
            panel_name=panel.name,
            panel_url=panel.url,
            panel_user=panel.username or "",
            panel_pass=panel.password or "",
            panel_token=getattr(panel, "token", None) or "",
            admin_password=admin.marzban_password or "",
        )


def suspendable_admins() -> list:
    """Sub-admins on a panel this module can suspend, for the picker."""
    with engin.sessionLocal() as session:
        types = {p.name: p.panel_type for p in crud.get_all_panels(session)}
        return [a for a in crud.get_all_admins(session) if types.get(a.panel) in SUPPORTED]


# ------------------------------------------------------------------ reading


async def _marzban_users(t: Target) -> list[dict]:
    """Every user the sub-admin owns, read in full or not at all."""
    sudo = MarzbanAPI(url=t.panel_url, username=t.panel_user, password=t.panel_pass)
    try:
        users = await sudo.get_all_users_paginated(owners=[t.username])
    except MarzbanAPIError as exc:
        # An older Marzban leaves the owner out of each user, which the
        # owner-filtered read refuses. The sub-admin's own login only ever
        # sees their own users, so read through that instead.
        if not t.admin_password:
            raise SuspendError(f"خواندن کاربران از مرزبان ناموفق بود: {exc}") from exc
        own = MarzbanAPI(url=t.panel_url, username=t.username, password=t.admin_password)
        try:
            users = await own.get_all_users_paginated()
        except Exception as exc2:
            raise SuspendError(f"خواندن کاربران از مرزبان ناموفق بود: {exc2}") from exc2
    except Exception as exc:
        raise SuspendError(f"خواندن کاربران از مرزبان ناموفق بود: {exc}") from exc
    owner = _name_key(t.username)
    return [
        u for u in users
        if isinstance(u, dict)
        and ("admin" not in u or _name_key((u.get("admin") or {}).get("username")) == owner)
    ]


async def _sanaei_clients(t: Target) -> list[dict]:
    """The sub-admin's 3x-ui clients. Errors raise: an empty list from a
    failed read must not look like a reseller with no users."""
    with engin.sessionLocal() as session:
        rows = crud.get_all_users_from_sanaei_table(session) or []
        owned = {r.username for r in rows if r.owner == t.username}
    api = SanaeiAPI(url=t.panel_url, token=t.panel_token)
    try:
        clients = await api.get_clients()
    except Exception as exc:
        raise SuspendError(f"خواندن کاربران از 3x-ui ناموفق بود: {exc}") from exc
    finally:
        await api.close()
    return [c for c in (clients or []) if isinstance(c, dict) and c.get("email") in owned]


async def active_users(t: Target) -> list[dict]:
    """The sub-admin's users that are switched on right now."""
    if t.panel_type == "marzban":
        return [u for u in await _marzban_users(t) if u.get("status") == "active" and u.get("username")]
    return [c for c in await _sanaei_clients(t) if c.get("enable") is True]


# ------------------------------------------------------------------ acting


async def _run_all(items: list, one: Callable[[object], Awaitable[str]], progress: Progress | None) -> Result:
    """Run `one` over items a few at a time; it returns done/failed/skipped."""
    result = Result(total=len(items))
    sem = asyncio.Semaphore(CONCURRENCY)
    lock = asyncio.Lock()
    finished = 0

    async def worker(item):
        nonlocal finished
        async with sem:
            try:
                outcome = await one(item)
            except Exception as exc:  # one user's failure never stops the rest
                logger.warning("suspend step failed for %r: %s", item, exc)
                outcome = "failed"
        async with lock:
            setattr(result, outcome, getattr(result, outcome) + 1)
            finished += 1
            if progress and (finished % 25 == 0 or finished == result.total):
                try:
                    await progress(finished, result.total)
                except Exception:
                    pass

    await asyncio.gather(*(worker(i) for i in items))
    return result


async def suspend_admin(
    admin_username: str, by: int | None = None, progress: Progress | None = None
) -> Result:
    """Disable every active user of the sub-admin. Raises SuspendError when
    their users could not be read; then nothing has been changed."""
    t = load_target(admin_username)
    users = await active_users(t)
    if not users:
        return Result()
    db.start_suspension(t.username, t.telegram_id, t.panel_type, by)

    if t.panel_type == "marzban":
        api = MarzbanAPI(url=t.panel_url, username=t.panel_user, password=t.panel_pass)

        async def one(user) -> str:
            key = user["username"]
            db.record_suspended_user(t.username, key)
            try:
                code = await api.set_user_status(key, "disabled")
            except Exception:
                code = 0
            if code == 200:
                db.mark_user_disabled(t.username, key)
                return "done"
            db.drop_suspended_user(t.username, key)
            return "failed"

        return await _run_all(users, one, progress)

    api = SanaeiAPI(url=t.panel_url, token=t.panel_token)

    async def one(client) -> str:
        key = client["email"]
        db.record_suspended_user(t.username, key, str(client.get("id") or ""))
        try:
            ok = await api.set_client_enable(client, False)
        except Exception:
            ok = False
        if ok:
            db.mark_user_disabled(t.username, key)
            return "done"
        db.drop_suspended_user(t.username, key)
        return "failed"

    try:
        return await _run_all(users, one, progress)
    finally:
        await api.close()


async def unsuspend_admin(admin_username: str, progress: Progress | None = None) -> Result:
    """Re-enable exactly the users suspend_admin disabled. A user deleted in
    the meantime is skipped. The suspension ends once nobody is left; users
    that failed stay recorded for the next try."""
    if db.get_suspension(admin_username) is None:
        raise SuspendError("این ساب‌ادمین قطع نیست")
    t = load_target(admin_username)
    pending = db.pending_suspended_users(t.username)

    if t.panel_type == "marzban":
        api = MarzbanAPI(url=t.panel_url, username=t.panel_user, password=t.panel_pass)

        async def one(row) -> str:
            key = row["user_key"]
            code = await api.set_user_status(key, "active")
            if code == 200:
                db.mark_user_restored(t.username, key)
                return "done"
            if code == 404:
                db.mark_user_restored(t.username, key)
                return "skipped"
            return "failed"

        result = await _run_all(pending, one, progress)
    else:
        by_email = {c.get("email"): c for c in await _sanaei_clients(t)}
        api = SanaeiAPI(url=t.panel_url, token=t.panel_token)

        async def one(row) -> str:
            key = row["user_key"]
            client = by_email.get(key)
            if client is None:
                db.mark_user_restored(t.username, key)
                return "skipped"
            if await api.set_client_enable(client, True):
                db.mark_user_restored(t.username, key)
                return "done"
            return "failed"

        try:
            result = await _run_all(pending, one, progress)
        finally:
            await api.close()

    if not db.pending_suspended_users(t.username):
        db.end_suspension(t.username)
    return result
