"""The "Top-up bot" section: run the reseller top-up bot from the panel.

The bot serves a management API in the same shape as the sales bots'
(see nexra-topup-bot/app/bot/api.py). The superadmin gives the panel its
address once; from then on the page's calls are forwarded to it with the key
the panel already shares with the bot (BOT_API_KEY), unless another one was
given. The key never reaches the browser, and only the superadmin gets in.
"""

import json
import os
import re
import threading

import httpx
from fastapi import APIRouter, Depends, Request
from fastapi.responses import JSONResponse, Response

from backend.auth.auth import get_current_admin
from backend.config import config
from backend.schema.output import ResponseModel
from backend.utils.logger import logger
from backend.utils.settings_store import DATA_DIR

router = APIRouter(prefix="/topup-bot", tags=["Top-up bot"])

# Kept out of settings.json, which the settings page hands to the browser.
CONNECTION_PATH = os.path.join(DATA_DIR, "topup-bot.json")
_lock = threading.Lock()

ALLOWED_RESOURCES = {
    "info", "stats", "settings", "texts", "buttons",
    "emoji", "emoji-pack", "emoji-sets",
}
SAFE_PATH = re.compile(r"^[A-Za-z0-9_\-.@%]+(/[A-Za-z0-9_\-.@%]+)*$")
TIMEOUT = httpx.Timeout(30.0, connect=10.0)


def _fail(code: int, message: str) -> JSONResponse:
    return JSONResponse(status_code=code, content={"success": False, "message": message})


def _superadmin_only(user: dict) -> JSONResponse | None:
    if user.get("role") != "superadmin":
        return _fail(403, "Access denied. Only superadmin can access this endpoint")
    return None


def load_connection() -> dict:
    try:
        with open(CONNECTION_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _save_connection(data: dict) -> None:
    with _lock:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = CONNECTION_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f)
        os.replace(tmp, CONNECTION_PATH)


def key_for(conn: dict) -> str:
    return conn.get("key") or config.BOT_API_KEY


def _normalize_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    for suffix in ("/api/v1", "/api"):
        if url.endswith(suffix):
            url = url[: -len(suffix)]
    return url.rstrip("/")


async def call(conn: dict, method: str, path: str, *, json_body: bool = False, **kwargs) -> httpx.Response:
    headers = {"Authorization": f"Bearer {key_for(conn)}"}
    if json_body:
        headers["Content-Type"] = "application/json"
    async with httpx.AsyncClient(timeout=TIMEOUT) as client:
        return await client.request(method, f"{conn['url']}/api/v1/{path}", headers=headers, **kwargs)


async def _probe(conn: dict) -> tuple[dict | None, str | None]:
    try:
        res = await call(conn, "GET", "info")
    except httpx.HTTPError as e:
        return None, f"Bot is unreachable: {e.__class__.__name__}"
    if res.status_code == 401:
        return None, "The bot rejected the key"
    try:
        body = res.json()
    except ValueError:
        return None, f"Not the top-up bot's API (HTTP {res.status_code})"
    if not body.get("ok") or (body.get("data") or {}).get("kind") != "topup":
        return None, body.get("error") or "Not the top-up bot's API"
    return body["data"], None


@router.get("/connection", description="Where the top-up bot is, and whether it answers (superadmin)")
async def get_connection(user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    conn = load_connection()
    if not conn.get("url"):
        return ResponseModel(success=True, message="ok", data={"url": "", "connected": False})
    info, error = await _probe(conn)
    return ResponseModel(
        success=True,
        message="ok",
        data={
            "url": conn["url"],
            "own_key": bool(conn.get("key")),
            "connected": info is not None,
            "error": error,
            "bot_username": (info or {}).get("bot_username"),
            "bot_name": (info or {}).get("bot_name"),
        },
    )


@router.put("/connection", description="Connect the top-up bot (superadmin)")
async def set_connection(body: dict, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    url = _normalize_url(str(body.get("url") or ""))
    if not url:
        _save_connection({})
        return ResponseModel(success=True, message="Disconnected", data={"url": "", "connected": False})
    if not url.startswith(("http://", "https://")):
        return _fail(400, "Bot address must start with http:// or https://")
    previous = load_connection()
    key = str(body.get("key") or "").strip() or (previous.get("key") if previous.get("url") == url else "")
    conn = {"url": url, "key": key}
    if not key_for(conn):
        return _fail(400, "Set BOT_API_KEY in the panel's .env, or give the bot's key here")
    info, error = await _probe(conn)
    if error:
        return _fail(400, error)
    _save_connection(conn)
    logger.info(f"Top-up bot connected: {url} (@{info.get('bot_username')})")
    return ResponseModel(
        success=True,
        message="Connected",
        data={"url": url, "own_key": bool(key), "connected": True, "error": None,
              "bot_username": info.get("bot_username"), "bot_name": info.get("bot_name")},
    )


@router.api_route("/api/{path:path}", methods=["GET", "PUT"], description="Top-up bot management API (superadmin)")
async def proxy(path: str, request: Request, user: dict = Depends(get_current_admin)):
    if denied := _superadmin_only(user):
        return denied
    conn = load_connection()
    if not conn.get("url"):
        return _fail(404, "The top-up bot is not connected yet")
    if not SAFE_PATH.match(path) or ".." in path.split("/"):
        return _fail(400, "Invalid path")
    if path.split("/", 1)[0] not in ALLOWED_RESOURCES:
        return _fail(404, "Unknown bot resource")

    body = await request.body()
    if len(body) > 2 * 1024 * 1024:
        return _fail(413, "Request is too large")
    try:
        res = await call(
            conn,
            request.method,
            path,
            params=list(request.query_params.multi_items()),
            content=body or None,
            json_body=bool(body),
        )
    except httpx.HTTPError as e:
        logger.warning(f"Top-up bot unreachable: {e!r}")
        return _fail(502, f"Bot is unreachable: {e.__class__.__name__}")

    ctype = res.headers.get("content-type", "")
    if not ctype.startswith("application/json"):
        if res.status_code == 200:
            # emoji previews
            return Response(
                content=res.content,
                media_type=ctype or "application/octet-stream",
                headers={"Cache-Control": "private, max-age=86400"},
            )
        return _fail(502, f"Unexpected answer from the bot (HTTP {res.status_code})")
    try:
        payload = res.json()
    except ValueError:
        return _fail(502, "Unexpected answer from the bot")
    if res.status_code == 401:
        # Never pass a 401 through: the page would log the user out of the panel.
        return _fail(502, "The bot rejected the panel's key; connect it again with the right key")
    if res.status_code >= 400 or not payload.get("ok"):
        return _fail(res.status_code if res.status_code >= 400 else 502, payload.get("error") or "Bot error")
    return JSONResponse(status_code=200, content={"success": True, "message": "ok", "data": payload.get("data")})
