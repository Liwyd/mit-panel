"""Keeps each Marzban admin's traffic in step with what is really on Marzban.

Nexra used to charge an admin only for the changes made through Nexra, so a
user created in Marzban itself, or by a sales bot logged in as the admin, cost
nothing. Now every admin has a ledger (MarzbanUsers) of the users Nexra has
charged them for, and any difference between it and Marzban is settled with
the same rules the Nexra handlers always used:

    new user            charge its data limit
    data limit changed  AdminLimiter.apply_update (committed = max(limit, used))
    usage reset         charge what had been used, up to the limit
    user gone           refund what was left unused (if delete_return_traffic)

The handlers settle the user they touch right before and after changing it
(refresh), and a background loop (marzban_sync_loop) settles everything else.
Reading every user is heavy for Marzban (it builds each user's links), so the
loop does that once per panel every MARZBAN_FULL_SYNC_INTERVAL. In between,
every MARZBAN_SYNC_INTERVAL, it reads only the newest users, which charges new
sales within about a minute; the same request reports how many users the
admins have in all, and when that no longer matches the ledger (a deletion,
mostly) a full read runs right away. Edits and resets of older users wait for
the next full read.
Charges outside Nexra are made even when the admin has no traffic left, so the
balance can go negative.

An admin's first sync only adopts the users already there, without charging:
they were either paid for through Nexra or made before this existed.
"""

import asyncio
import time
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from backend.config import config
from backend.db import crud
from backend.db.engin import sessionLocal
from backend.db.model import MarzbanUsers
from backend.services.limit_handler import AdminLimiter
from backend.services.marzban.api import APIService
from backend.utils.logger import logger

GB = 1024**3
# How many of the newest users the quick check reads per panel.
NEWEST_PAGE = 100
# Least time between two full reads of a panel that the quick check asks for.
FULL_SYNC_MIN_GAP = 120

# Counts the handlers' ledger writes per admin. The sync reads Marzban off the
# event loop, and a handler that settles a user meanwhile makes that read
# stale; the sync sees the count move and leaves the admin to its next pass.
_writes: dict[str, int] = {}


def _state(user: dict) -> tuple[int, int]:
    return int(user.get("data_limit") or 0), int(user.get("used_traffic") or 0)


def _name_key(name: str | None) -> str:
    # Marzban on MySQL matches admin names regardless of case, so "Abolfazl" in
    # Nexra logs in as "abolfazl" there; names are compared the same way here.
    return (name or "").strip().lower()


def _owned_by(user: dict, admin_username: str) -> bool:
    # Older Marzban leaves the admin out of a user; then the user is taken as
    # belonging to whoever was able to read it.
    if "admin" not in user:
        return True
    return _name_key((user.get("admin") or {}).get("username")) == _name_key(admin_username)


def _created_at(user: dict) -> datetime | None:
    """When Marzban made the user, as naive UTC like marzban_synced_at."""
    try:
        stamp = datetime.fromisoformat(str(user.get("created_at")).replace("Z", "+00:00"))
    except ValueError:
        return None
    if stamp.tzinfo is not None:
        stamp = stamp.astimezone(timezone.utc).replace(tzinfo=None)
    return stamp


def settle(
    db: Session,
    limiter: AdminLimiter,
    owner: str,
    username: str,
    user: dict | None,
    row: MarzbanUsers | None,
    synced_at: datetime | None = None,
) -> None:
    """Bring one ledger row in line with the user as Marzban has it now
    (None: no longer there for this admin), charging or refunding the
    difference. The caller commits.

    A user missing from the ledger but made before the admin's first sync
    (synced_at) is adopted without charging, like that sync would have: it
    was missed then, not created since."""
    if user is None:
        if row is not None:
            db.delete(row)
            limiter.increase_usage(max(row.data_limit - row.used_traffic, 0))
        return

    limit, used = _state(user)
    if row is None:
        db.add(MarzbanUsers(owner=owner, username=username, data_limit=limit, used_traffic=used))
        created = _created_at(user)
        # Marzban gives whole seconds; a user made in the sync's own second is new.
        if not (synced_at and created and created < synced_at.replace(microsecond=0)):
            limiter.charge(limit)
        return

    old_limit, old_used = row.data_limit, row.used_traffic
    if (limit, used) == (old_limit, old_used):
        return
    # The row is updated before charging: the limiter commits, and a charge
    # committed beside a stale row would be charged again on the next pass.
    row.data_limit, row.used_traffic = limit, used
    if used < old_used:
        # Only a reset lowers used traffic; what had been used is free again.
        limiter.charge(min(old_used, old_limit))
    if limit != old_limit:
        limiter.apply_update(old_limit, limit, used)


async def refresh(
    db: Session, admin_username: str, api: APIService, username: str, before_change: bool = False
) -> None:
    """Settle one user as `api` (the admin's own Marzban login) sees it now.

    Handlers call this before a change (before_change=True), so the ledger
    starts from Marzban's current state, and after it, to charge for the
    change. If Marzban can't be read the ledger is left alone and the next
    sync settles the user instead.
    """
    try:
        user = await api.find_user(username)
    except Exception as exc:
        logger.warning(f"Marzban ledger: could not read {username} for {admin_username}: {exc}")
        return
    if user is not None and not _owned_by(user, admin_username):
        user = None

    _writes[admin_username] = _writes.get(admin_username, 0) + 1
    row = crud.get_marzban_ledger_row(db, admin_username, username)
    admin = crud.get_admin_by_username(db, admin_username)
    if before_change and row is None and user is not None and admin.marzban_synced_at is None:
        # Not synced yet, so this user predates the ledger (the first sync
        # would adopt it free too); it isn't new.
        limit, used = _state(user)
        db.add(MarzbanUsers(owner=admin_username, username=username, data_limit=limit, used_traffic=used))
        db.commit()
        return
    settle(db, AdminLimiter(db, admin_username), admin_username, username, user, row, admin.marzban_synced_at)
    db.commit()


def _owner(user: dict) -> str | None:
    return (user.get("admin") or {}).get("username")


async def _confirm_gone(
    api: APIService, owner: str, found: dict[str, dict], known: set[str]
) -> set[str]:
    """Which ledger users missing from the list are really gone. Each is looked
    up on its own first: one bad or shifting page must not refund (and then
    re-charge) users that are still there. Fills `found` with the rest."""
    gone = set()
    for username in known - found.keys():
        user = await api.find_user(username)
        if user is None or not _owned_by(user, owner):
            gone.add(username)
        else:
            found[username] = user
    return gone


async def _read_newest(
    panel_url: str, panel_username: str, panel_password: str, owners: list[str]
) -> tuple[dict[str, dict[str, dict]], int | None]:
    """The quick check: the newest users of these owners, by owner, and how
    many users the owners have in all (None if Marzban can't be trusted to
    have filtered by owner). One small request either way."""
    api = APIService(panel_url, panel_username, panel_password)
    users, total = await api.list_newest_users(NEWEST_PAGE, admins=[owner.strip() for owner in owners])
    if any("admin" not in user for user in users):
        return {}, None  # No owner on the users; the full sync reads per admin.
    by_owner: dict[str, dict[str, dict]] = {owner: {} for owner in owners}
    names = {_name_key(owner): owner for owner in owners}
    filtered = True
    for user in users:
        owner = names.get(_name_key(_owner(user)))
        if owner and user.get("username"):
            by_owner[owner][user["username"]] = user
        else:
            filtered = False  # Marzban ignored the owner filter; total is everyone's.
    return by_owner, total if filtered else None


async def _read_panel(
    panel_url: str,
    panel_username: str,
    panel_password: str,
    owners: dict[str, str | None],
    known: dict[str, set[str]],
) -> dict[str, tuple[dict[str, dict], set[str]]]:
    """Every user of these owners on one Marzban, in one listing for the whole
    panel: {owner: (users by name, ledger users that are gone)}. An owner
    missing from the result couldn't be read and is left alone this time."""
    api = APIService(panel_url, panel_username, panel_password)
    users = await api.list_users(admins=[owner.strip() for owner in owners])
    result = {}
    if any("admin" not in user for user in users):
        # This Marzban doesn't say who owns a user, so ask as each admin.
        for owner, password in owners.items():
            own_api = APIService(panel_url, owner.strip(), password or "")
            try:
                found = {u["username"]: u for u in await own_api.list_users() if u.get("username")}
                result[owner] = (found, await _confirm_gone(own_api, owner, found, known[owner]))
            except Exception as exc:
                logger.warning(f"Marzban sync: could not read users of {owner}: {exc}")
        return result

    by_owner: dict[str, dict[str, dict]] = {owner: {} for owner in owners}
    names = {_name_key(owner): owner for owner in owners}
    for user in users:
        owner = names.get(_name_key(_owner(user)))
        if owner and user.get("username"):
            by_owner[owner][user["username"]] = user
    for owner, found in by_owner.items():
        try:
            result[owner] = (found, await _confirm_gone(api, owner, found, known[owner]))
        except Exception as exc:
            logger.warning(f"Marzban sync: could not check deleted users of {owner}: {exc}")
    return result


def _apply(
    panel_name: str, owner: str, found: dict[str, dict], gone: set[str], full: bool, read_at: datetime
) -> None:
    db = sessionLocal()
    try:
        admin = crud.get_admin_by_username(db, owner)
        if admin is None or admin.panel != panel_name:
            return
        ledger = crud.get_marzban_ledger(db, owner)

        if admin.marzban_synced_at is None:
            # Only a full read may adopt: a page of new users isn't all of them.
            if not full:
                return
            for username, user in found.items():
                limit, used = _state(user)
                row = ledger.get(username)
                if row is None:
                    db.add(MarzbanUsers(owner=owner, username=username, data_limit=limit, used_traffic=used))
                else:
                    row.data_limit, row.used_traffic = limit, used
            # When the read began: a user made while it ran may be missing
            # from it, and must still count as new afterwards.
            admin.marzban_synced_at = read_at
            db.commit()
            logger.info(f"Marzban sync: adopted {len(found)} existing users of {owner} without charging")
            return

        limiter = AdminLimiter(db, owner)
        before = admin.traffic
        for username, user in found.items():
            settle(db, limiter, owner, username, user, ledger.get(username), admin.marzban_synced_at)
        for username in gone:
            if username in ledger:
                settle(db, limiter, owner, username, None, ledger[username])
        db.commit()

        change = before - admin.traffic
        if change:
            verb = "charged" if change > 0 else "refunded"
            logger.info(
                f"Marzban sync: {owner} {verb} {abs(change) / GB:.2f} GB "
                f"for changes made outside Nexra, remaining {admin.traffic / GB:.2f} GB"
            )
    finally:
        db.close()


async def sync_panel(panel_name: str, full: bool) -> bool:
    """Read one panel and settle what changed. A full read settles everything;
    a quick one settles the newest users and returns True when the owners'
    user count on Marzban no longer matches the ledger, which means something
    beyond them changed (usually a deletion) and a full read is due."""
    db = sessionLocal()
    try:
        panel = crud.get_panel_by_name(db, panel_name)
        if not panel or panel.panel_type != "marzban" or not panel.is_active:
            return False
        admins = [a for a in crud.get_all_admins(db) if a.panel == panel_name]
        if not full:
            admins = [a for a in admins if a.marzban_synced_at is not None]
        owners = {a.username: a.marzban_password for a in admins}
        known = {o: set(crud.get_marzban_ledger(db, o)) for o in owners} if full else {}
        connection = (panel.url, panel.username, panel.password)
    finally:
        db.close()
    if not owners:
        return False

    writes = {o: _writes.get(o, 0) for o in owners}
    read_at = datetime.utcnow()
    total = None
    try:
        if full:
            result = await asyncio.to_thread(
                lambda: asyncio.run(_read_panel(*connection, owners, known))
            )
        else:
            newest, total = await asyncio.to_thread(
                lambda: asyncio.run(_read_newest(*connection, list(owners)))
            )
            result = {owner: (found, set()) for owner, found in newest.items()}
    except Exception as exc:
        logger.warning(f"Marzban sync: could not read panel {panel_name}: {exc}")
        return False

    for owner, (found, gone) in result.items():
        # A handler settled this admin's users while Marzban was being read,
        # so the read may be stale for them; the next pass picks them up.
        if _writes.get(owner, 0) != writes[owner]:
            continue
        try:
            _apply(panel_name, owner, found, gone, full, read_at)
        except Exception as exc:
            logger.error(f"Marzban sync failed for {owner}: {exc}")

    if total is None:
        return False
    db = sessionLocal()
    try:
        recorded = db.query(MarzbanUsers).filter(MarzbanUsers.owner.in_(list(owners))).count()
    finally:
        db.close()
    return recorded != total


# When each panel last had a full read (time.monotonic()).
_last_full: dict[str, float] = {}


async def sync_all(full: bool | None = None) -> None:
    """full=None is the schedule: a quick check, and a full read when it's
    due or the quick check found the count off (at most every
    FULL_SYNC_MIN_GAP seconds, so a count that never matches can't turn every
    quick check into a full read). True or False forces one kind."""
    db = sessionLocal()
    try:
        names = [p.name for p in crud.get_all_panels(db) if p.panel_type == "marzban" and p.is_active]
    finally:
        db.close()
    for name in names:
        since_full = time.monotonic() - _last_full.get(name, float("-inf"))
        run_full = full is True or (full is None and since_full >= config.MARZBAN_FULL_SYNC_INTERVAL)
        if not run_full:
            count_off = await sync_panel(name, full=False)
            run_full = full is None and count_off and since_full >= FULL_SYNC_MIN_GAP
        if run_full:
            _last_full[name] = time.monotonic()
            await sync_panel(name, full=True)


async def marzban_sync_loop():
    if config.MARZBAN_SYNC_INTERVAL <= 0:
        return
    # Let the app finish starting before the first (and largest) read.
    await asyncio.sleep(10)
    while True:
        try:
            await sync_all()
        except Exception as exc:
            logger.error(f"Marzban sync error: {exc}")
        await asyncio.sleep(config.MARZBAN_SYNC_INTERVAL)
