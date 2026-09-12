"""File-based storage for announcement banner images.

Mirrors how the login logo is stored (backend/utils/settings_store.py): raw
bytes on disk with no extension, media type sniffed from the file's own header
when served. One file per news row, named by that row's id, so no DB
migration is needed - a banner simply exists or doesn't for a given id.
"""

import os

DATA_DIR = os.environ.get("MITPANEL_DATA_DIR", "/app/data")
BANNERS_DIR = os.path.join(DATA_DIR, "banners")


def _banner_path(news_id: int) -> str:
    return os.path.join(BANNERS_DIR, str(news_id))


def save_banner(news_id: int, content: bytes) -> None:
    os.makedirs(BANNERS_DIR, exist_ok=True)
    with open(_banner_path(news_id), "wb") as f:
        f.write(content)


def delete_banner(news_id: int) -> None:
    path = _banner_path(news_id)
    if os.path.exists(path):
        os.remove(path)


def get_banner_path(news_id: int):
    path = _banner_path(news_id)
    return path if os.path.exists(path) else None


def banner_media_type(news_id: int) -> str:
    path = get_banner_path(news_id)
    if not path:
        return "application/octet-stream"
    try:
        with open(path, "rb") as f:
            head = f.read(16)
    except Exception:
        return "image/png"
    if head.startswith(b"\x89PNG"):
        return "image/png"
    if head.startswith(b"\xff\xd8"):
        return "image/jpeg"
    if head.startswith(b"GIF8"):
        return "image/gif"
    if head[:4] == b"RIFF" and b"WEBP" in head:
        return "image/webp"
    if head.startswith(b"<svg") or head.startswith(b"<?xml"):
        return "image/svg+xml"
    return "image/png"
