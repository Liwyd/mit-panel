"""The "Bot" section: run Nexra sales bots (nexrabot) from the panel.

The superadmin connects a bot (its address plus the two keys from the bot's
config) and assigns it to an admin. From then on the panel forwards the
page's calls to the bot's management API:

* superadmin -> the bot's owner key: everything, including the bot's VPN
  panels (servers);
* the assigned admin -> the bot's manager key: products, prices, payments,
  users, texts, buttons... The bot refuses panel changes for that key, and
  this proxy refuses them as well before they ever leave the panel.

The keys never reach the browser.
"""

import json
import os
import re
import tempfile
from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, File, Request, UploadFile, status
from fastapi.responses import FileResponse, JSONResponse, Response
from sqlalchemy.orm import Session

from backend.auth.auth import get_current_admin
from backend.db import crud
from backend.db.engin import get_db
from backend.db.model import Admins, TelegramBots
from backend.schema._input import TelegramBotInput, TelegramBotUpdateInput
from backend.schema.output import ResponseModel, TelegramBotOutput
from backend.utils.logger import logger
from backend.utils.settings_store import DATA_DIR

router = APIRouter(prefix="/sales-bots", tags=["Sales bots"])

APK_PATH = os.path.join(DATA_DIR, "nexra-autopay.apk")
APK_META_PATH = os.path.join(DATA_DIR, "nexra-autopay.json")
APK_RELEASE_REPO = os.environ.get("AUTOPAY_APK_REPO", "MHBehzadian/nexra-mirzabot")
APK_MAX_BYTES = 100 * 1024 * 1024

# First path segment of every bot API resource the panel may reach.
ALLOWED_RESOURCES = {
    "info", "stats", "settings", "texts", "buttons", "products", "categories",
    "giftcodes", "discounts", "help", "users", "services", "payments",
    "payment-settings", "cancel-requests", "autopay", "affiliates", "broadcast",
    "admins", "panels", "emoji", "emoji-pack", "emoji-allow", "button-styles",
}
# Resources an admin may only read (writing them is the superadmin's).
READ_ONLY_FOR_ADMINS = {"panels"}
SAFE_PATH = re.compile(r"^[A-Za-z0-9_\-.@%]+(/[A-Za-z0-9_\-.@%]+)*$")
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _fail(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"success": False, "message": message})


def _is_superadmin(user: dict) -> bool:
    return user.get("role") == "superadmin"


def _normalize_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


def _output(db: Session, bot: TelegramBots, superadmin: bool) -> TelegramBotOutput:
    admin_username = None
    if bot.admin_id:
        admin = db.query(Admins).filter(Admins.id == bot.admin_id).first()
        admin_username = admin.username if admin else None
    return TelegramBotOutput(
        id=bot.id,
        name=bot.name,
        url=bot.url if superadmin else None,
        admin_id=bot.admin_id,
        admin_username=admin_username,
        bot_username=bot.bot_username,
        is_active=bool(bot.is_active),
        created_at=bot.created_at,
    )


async def _probe(url: str, key: str) -> tuple[str | None, dict | str]:
    """GET /api/v1/info with key -> (role, info) or (None, reason)."""
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.get(f"{url}/api/v1/info", headers={"Authorization": f"Bearer {key}"})
    except httpx.HTTPError as e:
        return None, f"Bot is unreachable: {e.__class__.__name__}"
    if res.status_code == 401:
        return None, "The bot rejected this key"
    try:
        body = res.json()
    except ValueError:
        return None, f"Not a Nexra bot API (HTTP {res.status_code})"
    if not body.get("ok"):
        return None, body.get("error") or f"HTTP {res.status_code}"
    data = body.get("data") or {}
    return data.get("role"), data


async def _verify_keys(url: str, owner_key: str, manager_key: str) -> tuple[dict | None, str | None]:
    role, info = await _probe(url, owner_key)
    if role != "owner":
        return None, "Owner key: " + (info if isinstance(info, str) else "this is not the owner key")
    role, minfo = await _probe(url, manager_key)
    if role != "manager":
        return None, "Manager key: " + (minfo if isinstance(minfo, str) else "this is not the manager key")
    return info, None


def _visible_bot(db: Session, user: dict, bot_id: int) -> TelegramBots | None:
    bot = crud.get_bot_by_id(db, bot_id)
    if not bot:
        return None
    if _is_superadmin(user):
        return bot
    admin = crud.get_admin_by_username(db, user.get("username"))
    if not admin or not admin.is_active or bot.admin_id != admin.id or not bot.is_active:
        return None
    return bot


# ---------------------------------------------------------------- listing


@router.get("", description="Bots the current user can manage")
async def list_bots(db: Session = Depends(get_db), user: dict = Depends(get_current_admin)):
    superadmin = _is_superadmin(user)
    if superadmin:
        bots = crud.get_all_bots(db)
    else:
        admin = crud.get_admin_by_username(db, user.get("username"))
        bots = crud.get_bots_for_admin(db, admin.id) if admin and admin.is_active else []
    return ResponseModel(
        success=True,
        message="Bots retrieved successfully",
        data=[_output(db, b, superadmin).model_dump(mode="json") for b in bots],
    )


# ---------------------------------------------------------------- superadmin: connections


@router.post("/manage", description="Connect a bot (superadmin)")
async def create_bot(
    bot_input: TelegramBotInput,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_admin),
):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    name = bot_input.name.strip()
    url = _normalize_url(bot_input.url)
    if not name:
        return _fail(400, "Name is required")
    if not url.startswith(("http://", "https://")):
        return _fail(400, "Bot address must start with https://")
    if crud.get_bot_by_name(db, name):
        return _fail(409, "A bot with this name already exists")
    if bot_input.admin_id is not None and not db.query(Admins).filter(Admins.id == bot_input.admin_id).first():
        return _fail(404, "Admin not found")
    info, err = await _verify_keys(url, bot_input.owner_key.strip(), bot_input.manager_key.strip())
    if err:
        return _fail(400, err)
    bot = crud.add_bot(
        db,
        name=name,
        url=url,
        owner_key=bot_input.owner_key.strip(),
        manager_key=bot_input.manager_key.strip(),
        admin_id=bot_input.admin_id,
        bot_username=info.get("bot_username"),
        is_active=bot_input.is_active,
    )
    logger.info(f"Bot connected: {name} ({url})")
    await _push_emoji_allow(db, bot)
    return ResponseModel(success=True, message="Bot connected", data=_output(db, bot, True).model_dump(mode="json"))


@router.put("/manage/{bot_id}", description="Change a bot connection (superadmin)")
async def update_bot(
    bot_id: int,
    bot_input: TelegramBotUpdateInput,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_admin),
):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    bot = crud.get_bot_by_id(db, bot_id)
    if not bot:
        return _fail(404, "Bot not found")
    values: dict = {}
    if bot_input.name is not None and bot_input.name.strip() and bot_input.name.strip() != bot.name:
        if crud.get_bot_by_name(db, bot_input.name.strip()):
            return _fail(409, "A bot with this name already exists")
        values["name"] = bot_input.name.strip()
    url = _normalize_url(bot_input.url) if bot_input.url else bot.url
    if not url.startswith(("http://", "https://")):
        return _fail(400, "Bot address must start with https://")
    owner_key = (bot_input.owner_key or "").strip() or bot.owner_key
    manager_key = (bot_input.manager_key or "").strip() or bot.manager_key
    if url != bot.url or owner_key != bot.owner_key or manager_key != bot.manager_key:
        info, err = await _verify_keys(url, owner_key, manager_key)
        if err:
            return _fail(400, err)
        values.update(url=url, owner_key=owner_key, manager_key=manager_key, bot_username=info.get("bot_username"))
    if bot_input.unassign:
        values["admin_id"] = None
    elif bot_input.admin_id is not None:
        if not db.query(Admins).filter(Admins.id == bot_input.admin_id).first():
            return _fail(404, "Admin not found")
        values["admin_id"] = bot_input.admin_id
    if bot_input.is_active is not None:
        values["is_active"] = bot_input.is_active
    bot = crud.update_bot(db, bot, **values)
    return ResponseModel(success=True, message="Bot updated", data=_output(db, bot, True).model_dump(mode="json"))


@router.delete("/manage/{bot_id}", description="Disconnect a bot (superadmin); the bot itself keeps running")
async def delete_bot(bot_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    if not crud.remove_bot(db, bot_id):
        return _fail(404, "Bot not found")
    return ResponseModel(success=True, message="Bot disconnected")


SHARED_IDS_PATH = os.path.join(DATA_DIR, "shared-admin-ids.json")


def _load_shared_ids() -> set[str]:
    """Telegram ids that are admin on every bot (the panel owner's own), as
    install.sh found them; they say nothing about who runs a bot."""
    try:
        with open(SHARED_IDS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return set()
    return {str(i) for i in data.get("ids", [])} if isinstance(data, dict) else set()


def _save_shared_ids(ids: set[str]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = SHARED_IDS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"ids": sorted(ids)}, f)
    os.replace(tmp, SHARED_IDS_PATH)


async def _guess_owner(db: Session, probe, ignore: set[str] | None = None) -> tuple[Admins | None, str]:
    """Which panel admin runs this bot.

    1. The bot sells from a Nexra Panel with some reseller's credentials: the
       panel admin with that username is the owner.
    2. Otherwise the panel admin whose Telegram id is one of the bot's admins
       (its main admin or the admin list), leaving out the ids in `ignore`
       (the panel owner's, which is admin on every bot) — when exactly one
       panel admin matches.
    """
    ignore = ignore or set()
    admins = crud.get_all_admins(db)
    by_name = {a.username.lower(): a for a in admins}
    code, panels = await _bot_call(probe, "GET", "panels")
    if code == 200:
        names = {str(p.get("username_panel") or "").lower() for p in panels.get("data") or [] if p.get("type") == "nexra"}
        found = [by_name[n] for n in names if n in by_name]
        if len(found) == 1:
            return found[0], f"its Nexra panel uses the reseller {found[0].username}"
        if len(found) > 1:
            return None, "it sells from several resellers: " + ", ".join(a.username for a in found)
    code, info = await _bot_call(probe, "GET", "info")
    main = str((info.get("data") or {}).get("admin_id") or "") if code == 200 else ""
    code, adm = await _bot_call(probe, "GET", "admins")
    ids = [main] + [str(x) for x in ((adm.get("data") or {}).get("admins") or [])] if code == 200 else [main]
    ids = [i.strip() for i in ids if i.strip().isdigit() and i.strip() not in ignore]
    matched: dict[int, tuple[Admins, str]] = {}
    for tid in ids:
        for a in admins:
            if a.telegram_id and str(a.telegram_id) == tid and a.id not in matched:
                matched[a.id] = (a, tid)
    if len(matched) == 1:
        a, tid = next(iter(matched.values()))
        return a, f"its admin's Telegram id {tid} belongs to {a.username}"
    if len(matched) > 1:
        return None, "its admins' Telegram ids belong to several panel admins: " + ", ".join(
            f"{a.username} ({tid})" for a, tid in matched.values())
    return None, "no panel admin matches its Nexra reseller or its admins' Telegram ids"


@router.post("/register", description="Connect or refresh a bot and give it to its owner automatically (superadmin; used by install.sh)")
async def register_bot(body: dict, db: Session = Depends(get_db), user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    url = _normalize_url(str(body.get("url", "")))
    owner_key, manager_key = str(body.get("owner_key", "")).strip(), str(body.get("manager_key", "")).strip()
    if not url.startswith(("http://", "https://")):
        return _fail(400, "Bot address must start with https://")
    info, err = await _verify_keys(url, owner_key, manager_key)
    if err:
        return _fail(400, err)
    probe = type("Probe", (), {"url": url, "owner_key": owner_key, "name": url})()
    shared = _load_shared_ids()
    given = {str(i).strip() for i in (body.get("ignore_ids") or []) if str(i).strip().isdigit()}
    if not given <= shared:
        shared |= given
        _save_shared_ids(shared)
    owner, reason = await _guess_owner(db, probe, shared)
    existing = next((b for b in crud.get_all_bots(db) if b.url == url), None)
    if existing:
        values = dict(owner_key=owner_key, manager_key=manager_key, bot_username=info.get("bot_username"))
        # an assignment made by hand is kept
        if existing.admin_id is None and owner:
            values["admin_id"] = owner.id
        bot = crud.update_bot(db, existing, **values)
        created = False
    else:
        name = str(body.get("name") or "").strip() or ("@" + info["bot_username"] if info.get("bot_username") else url)
        base, n = name, 2
        while crud.get_bot_by_name(db, name):
            name, n = f"{base} ({n})", n + 1
        bot = crud.add_bot(db, name=name, url=url, owner_key=owner_key, manager_key=manager_key,
                           admin_id=owner.id if owner else None, bot_username=info.get("bot_username"), is_active=True)
        created = True
    await _push_emoji_allow(db, bot)
    logger.info(f"Bot registered: {bot.name} ({url}) owner={owner.username if owner else None} ({reason})")
    out = _output(db, bot, True).model_dump(mode="json")
    return ResponseModel(success=True, message="Bot registered", data={"bot": out, "created": created,
                                                                        "assigned_to": out.get("admin_username"), "reason": reason})


@router.post("/manage/{bot_id}/check", description="Re-check a bot's address and keys (superadmin)")
async def check_bot(bot_id: int, db: Session = Depends(get_db), user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    bot = crud.get_bot_by_id(db, bot_id)
    if not bot:
        return _fail(404, "Bot not found")
    info, err = await _verify_keys(bot.url, bot.owner_key, bot.manager_key)
    if err:
        return _fail(502, err)
    if info.get("bot_username") and info.get("bot_username") != bot.bot_username:
        crud.update_bot(db, bot, bot_username=info.get("bot_username"))
    await _push_emoji_allow(db, bot)
    return ResponseModel(success=True, message="Bot is reachable", data=info)


# ---------------------------------------------------------------- premium emoji packs
#
# The superadmin picks which custom emoji packs the bots may use. Packs are
# resolved through a connected bot (Telegram only answers bots), kept here,
# and the union of their emoji ids is pushed to every bot, which then refuses
# any other premium emoji — from the panel and from its own Telegram menu.
# Until a pack list is saved for the first time nothing is pushed and the
# bots keep their old, unrestricted behaviour.

PACKS_PATH = os.path.join(DATA_DIR, "emoji-packs.json")
PACK_NAME = re.compile(r"^[A-Za-z0-9_]{1,64}$")


def _load_packs() -> list[dict] | None:
    try:
        with open(PACKS_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return None
    return data.get("packs") if isinstance(data, dict) and isinstance(data.get("packs"), list) else None


def _save_packs(packs: list[dict]) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = PACKS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump({"packs": packs}, f, ensure_ascii=False)
    os.replace(tmp, PACKS_PATH)


def _pack_name(link: str) -> str:
    return (link or "").strip().rstrip("/").split("/")[-1].split("?")[0]


async def _bot_call(bot: TelegramBots, method: str, path: str, body: dict | None = None) -> tuple[int, dict]:
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.request(method, f"{bot.url}/api/v1/{path}", json=body,
                                       headers={"Authorization": f"Bearer {bot.owner_key}"})
        return res.status_code, res.json()
    except (httpx.HTTPError, ValueError) as e:
        return 502, {"ok": False, "error": f"Bot is unreachable: {e.__class__.__name__}"}


async def _push_emoji_allow(db: Session, only: TelegramBots | None = None) -> list[dict]:
    """Send the allowed emoji ids to every bot (or one). Returns per-bot results."""
    packs = _load_packs()
    if packs is None:
        return []
    ids = sorted({e["id"] for p in packs for e in p.get("emojis", [])})
    results = []
    for bot in [only] if only else crud.get_all_bots(db):
        code, body = await _bot_call(bot, "PUT", "emoji-allow", {"ids": ids})
        results.append({"bot": bot.name, "ok": code == 200, "error": None if code == 200 else body.get("error")})
        if code != 200:
            logger.warning(f"emoji allow-list not pushed to {bot.name}: {body.get('error')}")
    return results


@router.get("/emoji-packs", description="The premium emoji packs bots may use")
async def list_packs(user: dict = Depends(get_current_admin)):
    packs = _load_packs()
    return ResponseModel(success=True, message="ok", data={"configured": packs is not None, "packs": packs or []})


EMOJI_ID = re.compile(r"(?<![0-9])[0-9]{15,25}(?![0-9])")
PACK_LINK = re.compile(r"(?:t\.me|telegram\.me)/(?:addemoji|addstickers)/([A-Za-z0-9_]{1,64})")


@router.post("/emoji-packs", description="Allow premium emoji packs (superadmin): a pack link or name, emoji ids, or the bot's emoji-id message")
async def add_pack(body: dict, db: Session = Depends(get_db), user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    text = str(body.get("link", "")).strip()
    names = PACK_LINK.findall(text)
    ids = list(dict.fromkeys(EMOJI_ID.findall(PACK_LINK.sub(" ", text))))
    if not names and not ids:
        name = _pack_name(text)
        if not PACK_NAME.match(name):
            return _fail(400, "لینک پک (t.me/addemoji/…)، نام پک یا شناسه‌ی ایموجی‌ها را بگذارید")
        names = [name]
    bots = [b for b in crud.get_all_bots(db) if b.is_active] or crud.get_all_bots(db)
    if not bots:
        return _fail(400, "Connect a bot first; packs are read through a bot")
    via = bots[0]
    if ids:
        code, res = await _bot_call(via, "GET", "emoji-sets?ids=" + ",".join(ids[:200]))
        if code == 404 or (code == 502 and "JSONDecodeError" in str(res.get("error"))):
            return _fail(400, "نسخه‌ی ربات قدیمی است و شناسه را نمی‌شناسد (روی سرور: bash install.sh update)؛ فعلاً لینک پک را بگذارید")
        if code != 200 or not res.get("ok"):
            return _fail(code if code >= 400 else 502, res.get("error") or "ایموجی‌ها پیدا نشدند")
        found = list(dict.fromkeys((res["data"].get("sets") or {}).values()))
        if not found and not names:
            return _fail(404, "تلگرام این شناسه‌ها را نمی‌شناسد")
        names += [n for n in found if n not in names]
    packs = _load_packs() or []
    have = {p["name"].lower() for p in packs}
    added, already = [], []
    for name in dict.fromkeys(names):
        if name.lower() in have:
            already.append(name)
            continue
        code, res = await _bot_call(via, "GET", f"emoji-pack/{name}")
        if code != 200 or not res.get("ok"):
            return _fail(code if code >= 400 else 502, f"{name}: " + (res.get("error") or "پک خوانده نشد"))
        data = res["data"]
        packs.append({"name": data["name"], "title": data.get("title") or data["name"],
                      "emojis": [{"id": e["id"], "emoji": e.get("emoji", "")} for e in data.get("emojis", [])]})
        have.add(data["name"].lower())
        added.append(data.get("title") or data["name"])
    if not added:
        return _fail(409, "این پک قبلاً اضافه شده: " + ", ".join(already))
    _save_packs(packs)
    pushed = await _push_emoji_allow(db)
    return ResponseModel(success=True, message="Pack added", data={"packs": packs, "pushed": pushed,
                                                                    "added": added, "already": already})


@router.delete("/emoji-packs/{name}", description="Remove an emoji pack (superadmin)")
async def remove_pack(name: str, db: Session = Depends(get_db), user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    packs = _load_packs() or []
    left = [p for p in packs if p["name"] != name]
    if len(left) == len(packs):
        return _fail(404, "Pack not found")
    _save_packs(left)
    pushed = await _push_emoji_allow(db)
    return ResponseModel(success=True, message="Pack removed", data={"packs": left, "pushed": pushed})


@router.post("/emoji-packs/sync", description="Send the allowed emoji to every bot again (superadmin)")
async def sync_packs(db: Session = Depends(get_db), user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    if _load_packs() is None:
        _save_packs([])
    return ResponseModel(success=True, message="ok", data={"pushed": await _push_emoji_allow(db)})


# ---------------------------------------------------------------- auto-confirm app


def _apk_meta() -> dict:
    meta: dict = {}
    try:
        with open(APK_META_PATH, "r", encoding="utf-8") as f:
            meta = json.load(f) or {}
    except (OSError, ValueError):
        meta = {}
    meta["available"] = os.path.isfile(APK_PATH)
    if meta["available"]:
        meta["size"] = os.path.getsize(APK_PATH)
    return meta


def _store_apk(data: bytes, meta: dict) -> None:
    os.makedirs(DATA_DIR, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=DATA_DIR, suffix=".apk")
    with os.fdopen(fd, "wb") as f:
        f.write(data)
    os.replace(tmp, APK_PATH)
    meta = dict(meta, updated_at=datetime.utcnow().isoformat() + "Z", size=len(data))
    with open(APK_META_PATH, "w", encoding="utf-8") as f:
        json.dump(meta, f)


@router.get("/autopay-app/info", description="Is the auto-confirm app available for download")
async def apk_info(user: dict = Depends(get_current_admin)):
    return ResponseModel(success=True, message="ok", data=_apk_meta())


@router.get("/autopay-app/download", description="Download the auto-confirm (SMS forwarder) Android app")
async def apk_download(user: dict = Depends(get_current_admin)):
    if not os.path.isfile(APK_PATH):
        return _fail(404, "The auto-confirm app has not been uploaded yet")
    return FileResponse(
        APK_PATH,
        media_type="application/vnd.android.package-archive",
        filename="nexra-autopay.apk",
    )


@router.post("/autopay-app/upload", description="Upload a new build of the auto-confirm app (superadmin)")
async def apk_upload(file: UploadFile = File(...), user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    if not (file.filename or "").lower().endswith(".apk"):
        return _fail(400, "Only .apk files are allowed")
    data = await file.read(APK_MAX_BYTES + 1)
    if len(data) > APK_MAX_BYTES:
        return _fail(413, "The file is too large")
    if not data.startswith(b"PK"):
        return _fail(400, "This is not an Android app (.apk) file")
    _store_apk(data, {"source": "upload", "file": file.filename})
    return ResponseModel(success=True, message="App uploaded", data=_apk_meta())


@router.post("/autopay-app/fetch", description="Fetch the latest app build from GitHub releases (superadmin)")
async def apk_fetch(user: dict = Depends(get_current_admin)):
    if not _is_superadmin(user):
        return _fail(status.HTTP_403_FORBIDDEN, "Access denied. Only superadmin can access this endpoint")
    api = f"https://api.github.com/repos/{APK_RELEASE_REPO}/releases?per_page=20"
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(120.0, connect=15.0), follow_redirects=True) as client:
            res = await client.get(api, headers={"Accept": "application/vnd.github+json"})
            if res.status_code != 200:
                return _fail(502, f"GitHub answered HTTP {res.status_code}")
            asset, tag = None, None
            for rel in res.json():
                if rel.get("draft"):
                    continue
                for a in rel.get("assets") or []:
                    if str(a.get("name", "")).lower().endswith(".apk"):
                        asset, tag = a, rel.get("tag_name")
                        break
                if asset:
                    break
            if not asset:
                return _fail(404, "No release with an .apk file was found")
            if int(asset.get("size") or 0) > APK_MAX_BYTES:
                return _fail(413, "The file is too large")
            dl = await client.get(asset["browser_download_url"])
            if dl.status_code != 200 or not dl.content.startswith(b"PK"):
                return _fail(502, "Downloading the app failed")
    except httpx.HTTPError as e:
        return _fail(502, f"GitHub is unreachable: {e.__class__.__name__}")
    _store_apk(dl.content, {"source": "github", "version": tag, "file": asset.get("name")})
    logger.info(f"Auto-confirm app {tag} fetched from GitHub")
    return ResponseModel(success=True, message="App updated", data=_apk_meta())


# ---------------------------------------------------------------- proxy to the bot


@router.api_route("/{bot_id}/api/{path:path}", methods=["GET", "POST", "PUT", "DELETE"], description="Bot management API")
async def proxy(
    bot_id: int,
    path: str,
    request: Request,
    db: Session = Depends(get_db),
    user: dict = Depends(get_current_admin),
):
    bot = _visible_bot(db, user, bot_id)
    if not bot:
        return _fail(404, "Bot not found")
    if not SAFE_PATH.match(path) or ".." in path.split("/"):
        return _fail(400, "Invalid path")
    resource = path.split("/", 1)[0]
    if resource not in ALLOWED_RESOURCES:
        return _fail(404, "Unknown bot resource")
    superadmin = _is_superadmin(user)
    if not superadmin and resource in READ_ONLY_FOR_ADMINS and request.method != "GET":
        return _fail(403, "Only the superadmin can change the bot's servers")
    if resource == "emoji-allow" and request.method != "GET":
        return _fail(403, "The allowed emoji follow the packs set in the panel")
    if resource == "emoji-pack" and not superadmin:
        allowed = {p["name"].lower() for p in (_load_packs() or [])}
        if path.split("/", 1)[-1].lower() not in allowed:
            return _fail(403, "Only the packs added by the panel owner can be used")

    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        return _fail(413, "Request is too large")
    key = bot.owner_key if superadmin else bot.manager_key
    headers = {"Authorization": f"Bearer {key}"}
    if body:
        headers["Content-Type"] = "application/json"
    target = f"{bot.url}/api/v1/{path}"
    try:
        async with httpx.AsyncClient(timeout=TIMEOUT) as client:
            res = await client.request(
                request.method, target, params=list(request.query_params.multi_items()), content=body or None, headers=headers
            )
    except httpx.HTTPError as e:
        logger.warning(f"Bot {bot.name} unreachable: {e!r}")
        return _fail(502, f"Bot is unreachable: {e.__class__.__name__}")

    ctype = res.headers.get("content-type", "")
    if not ctype.startswith("application/json"):
        if res.status_code == 200:
            # receipt photos
            return Response(
                content=res.content,
                media_type=ctype or "application/octet-stream",
                headers={"Cache-Control": "private, max-age=3600"},
            )
        return _fail(502, f"Unexpected answer from the bot (HTTP {res.status_code})")
    try:
        payload = res.json()
    except ValueError:
        return _fail(502, "Unexpected answer from the bot")
    if res.status_code == 401:
        # Never pass a 401 through: the page would log the user out of the panel.
        return _fail(502, "The bot rejected the panel's key; ask the superadmin to re-connect it")
    if res.status_code >= 400 or not payload.get("ok"):
        return _fail(res.status_code if res.status_code >= 400 else 502, payload.get("error") or "Bot error")
    return JSONResponse(status_code=200, content={"success": True, "message": "ok", "data": payload.get("data")})
