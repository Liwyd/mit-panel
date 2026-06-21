import asyncio
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from backend.config import config
from backend.auth import auth_router
from backend.api import roter_list


app = FastAPI(
    title="WalPanel",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


for router in roter_list:
    app.include_router(router, prefix=f"/{config.URLPATH}")
app.include_router(auth_router, prefix=f"/{config.URLPATH}")


# Serve frontend
frontend_build_path = Path(__file__).parent.parent / "frontend" / "dist"
app.mount(
    f"/{config.URLPATH}/assets",
    StaticFiles(directory=frontend_build_path / "assets"),
    name="static",
)
index_html_path = frontend_build_path / "index.html"


@app.get(f"/{config.URLPATH}")
@app.get(f"/{config.URLPATH}/{{path_name:path}}")
async def serve_frontend(path_name: str = ""):
    if index_html_path.exists():
        return FileResponse(index_html_path)
    return {"error": "Frontend build not found"}


@app.on_event("startup")
async def _start_background_tasks():
    # Periodic Telegram backup (configurable from Settings)
    from backend.services.backup_scheduler import backup_scheduler

    asyncio.create_task(backup_scheduler())
