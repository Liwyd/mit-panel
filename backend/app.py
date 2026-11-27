import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from starlette.types import Scope

from backend.config import config
from backend.auth import auth_router
from backend.api import roter_list


app = FastAPI(
    title="MIT Panel",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
# The frontend bundle (~1 MB) and the user lists were sent uncompressed; gzip
# shrinks both to roughly a third. Small responses aren't worth compressing.
app.add_middleware(GZipMiddleware, minimum_size=1024)


for router in roter_list:
    app.include_router(router, prefix=f"/{config.URLPATH}")
app.include_router(auth_router, prefix=f"/{config.URLPATH}")


class _HashedAssets(StaticFiles):
    """Vite puts a content hash in every file name under /assets, so a name
    never changes meaning: browsers may keep them for good and skip asking."""

    async def get_response(self, path: str, scope: Scope):
        response = await super().get_response(path, scope)
        if response.status_code in (200, 304):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


# index.html names the current hashed bundle, so it must be re-checked on every
# visit or a browser would keep loading the previous release after a deploy.
_NO_CACHE = {"Cache-Control": "no-cache"}

# Serve frontend
frontend_build_path = Path(__file__).parent.parent / "frontend" / "dist"
app.mount(
    f"/{config.URLPATH}/assets",
    _HashedAssets(directory=frontend_build_path / "assets"),
    name="static",
)
index_html_path = frontend_build_path / "index.html"

# Vite copies frontend/public/* (favicon, PWA icons, manifest) to the root of
# the build, and index.html links them as /{URLPATH}/<name>. Only /assets is
# mounted above, so without this they fell through to the SPA catch-all and
# came back as index.html. The allowlist is fixed at startup from the files
# actually in the build root: a request can only ever name one of those
# files, never a path, so there is nothing to traverse.
_PUBLIC_MEDIA_TYPES = {".webmanifest": "application/manifest+json"}


def _public_root_files(build_path: Path) -> dict[str, Path]:
    if not build_path.is_dir():
        return {}
    return {
        p.name: p
        for p in build_path.iterdir()
        if p.is_file() and p.name != "index.html"
    }


_public_files = _public_root_files(frontend_build_path)


@app.get(f"/{config.URLPATH}")
@app.get(f"/{config.URLPATH}/{{path_name:path}}")
async def serve_frontend(path_name: str = ""):
    public_file = _public_files.get(path_name)
    if public_file is not None and public_file.is_file():
        return FileResponse(
            public_file,
            media_type=_PUBLIC_MEDIA_TYPES.get(public_file.suffix),
        )
    if index_html_path.exists():
        return FileResponse(index_html_path, headers=_NO_CACHE)
    return {"error": "Frontend build not found"}


@app.on_event("startup")
async def _start_background_tasks():
    # Create/refresh the bot-owned tables (analytics included) even when no
    # Telegram bot is configured: the analytics page needs its tables on a
    # bot-less install too. Idempotent DDL, and synchronous on this thread, so
    # the bot's own later init_db() runs after it rather than beside it.
    #
    # Guarded: a failure here must degrade the analytics page, never refuse to
    # boot a panel that is already serving people.
    from backend.bot import db as bot_db
    from backend.utils.logger import logger

    try:
        bot_db.init_db()
    except Exception:
        logger.exception("init_db failed at startup; some tables may be missing")

    # Periodic Telegram backup (configurable from Settings)
    from backend.services.backup_scheduler import backup_scheduler

    asyncio.create_task(backup_scheduler())

    # Read-only recorder feeding the Analytics usage charts (never charges).
    # Supervised like every other background loop, so a crash restarts it.
    from backend.bot.service import _supervised
    from backend.services.marzban.usage_recorder import run_usage_recorder

    asyncio.create_task(_supervised("usage_recorder", run_usage_recorder))

    # Start top-up bot if BOT_TOKEN is configured
    from backend.bot.service import start_bot

    start_bot()
