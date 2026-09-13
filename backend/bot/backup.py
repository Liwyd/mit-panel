"""Backing up everything the bot owns: its database and the receipt images."""

from __future__ import annotations

import os
import sqlite3
import tarfile
import tempfile
from datetime import datetime

from backend.bot.config import bot_config

MAX_UPLOAD_BYTES = 45 * 1024 * 1024


def _snapshot_db(destination: str) -> None:
    source = sqlite3.connect(bot_config.sqlite_path)
    target = sqlite3.connect(destination)
    try:
        with target:
            source.backup(target)
    finally:
        target.close()
        source.close()


def create_backup(stamp: str | None = None) -> tuple[str, bool]:
    """Build a .tar.gz of the bot's state.

    Returns (archive_path, media_included).
    """
    stamp = stamp or datetime.now().strftime("%Y%m%d-%H%M%S")
    workdir = tempfile.mkdtemp(prefix="mit-bot-backup-")
    db_snapshot = os.path.join(workdir, "mitpanel.db")
    _snapshot_db(db_snapshot)

    media_dir = bot_config.media_dir
    media_size = 0
    if os.path.isdir(media_dir):
        for root, _, files in os.walk(media_dir):
            for name in files:
                media_size += os.path.getsize(os.path.join(root, name))

    include_media = os.path.isdir(media_dir) and media_size < MAX_UPLOAD_BYTES
    archive_path = os.path.join(workdir, f"mit-bot-backup-{stamp}.tar.gz")
    with tarfile.open(archive_path, "w:gz") as tar:
        tar.add(db_snapshot, arcname="mitpanel.db")
        if include_media:
            tar.add(media_dir, arcname="media")

    return archive_path, include_media
