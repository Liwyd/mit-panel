"""Broadcast logic: build the send plan from a draft and deliver it.

The draft is a list of ``{"id", "forwarded", "group"}`` entries — message ids
in the superadmin's chat with the bot. Delivery re-sends those messages with
copyMessages / forwardMessages, so every content type works and captions,
entities and albums are kept exactly.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Awaitable, Callable

from aiogram import Bot
from aiogram.exceptions import TelegramForbiddenError, TelegramRetryAfter

from backend.bot import db, texts

logger = logging.getLogger(__name__)

MAX_DRAFT = 50
CHUNK = 100
PACE_SECONDS = 0.05  # ~20 recipients per second
MAX_TRIES = 3

_running = False
_tasks: set[asyncio.Task] = set()


def plan(draft: list[dict]) -> list[tuple[bool, list[int]]]:
    """Consecutive runs sharing `forwarded`, chunked at CHUNK ids."""
    runs: list[tuple[bool, list[int]]] = []
    for item in draft:
        forwarded = bool(item.get("forwarded"))
        if runs and runs[-1][0] == forwarded:
            runs[-1][1].append(item["id"])
        else:
            runs.append((forwarded, [item["id"]]))
    batches: list[tuple[bool, list[int]]] = []
    for forwarded, ids in runs:
        for i in range(0, len(ids), CHUNK):
            batches.append((forwarded, ids[i : i + CHUNK]))
    return batches


async def send_draft(bot: Bot, chat_id: int, from_chat_id: int, draft: list[dict]) -> None:
    """Deliver the whole draft to one chat. RetryAfter is waited out per batch
    (so nothing already delivered is sent twice); other errors propagate."""
    for forwarded, ids in plan(draft):
        send = bot.forward_messages if forwarded else bot.copy_messages
        for attempt in range(1, MAX_TRIES + 1):
            try:
                await send(chat_id, from_chat_id, message_ids=ids)
                break
            except TelegramRetryAfter as exc:
                if attempt == MAX_TRIES:
                    raise
                await asyncio.sleep(exc.retry_after)


def audience(kind: str) -> list[int]:
    """Who receives it. Superadmins are left out: they already saw the
    preview, and the counts on the buttons should match what is sent."""
    from backend.bot.config import bot_config

    users = db.list_linked_users() if kind == "linked" else db.list_known_users()
    admins = set(bot_config.superadmin_id_list)
    return [u for u in users if u not in admins]


def is_running() -> bool:
    return _running


def try_acquire() -> bool:
    """Single-broadcast guard; synchronous, so check-and-set cannot interleave."""
    global _running
    if _running:
        return False
    _running = True
    return True


def release() -> None:
    global _running
    _running = False


async def run_broadcast(
    bot: Bot, owner_id: int, draft: list[dict], recipients: list[int]
) -> None:
    """Send to every recipient, then report to the owner. Never raises."""
    started = time.monotonic()
    sent = blocked = failed = 0
    targets = [r for r in dict.fromkeys(recipients) if r != owner_id]
    try:
        for chat_id in targets:
            try:
                await send_draft(bot, chat_id, owner_id, draft)
                sent += 1
            except TelegramForbiddenError:
                blocked += 1
            except Exception:
                logger.exception("broadcast to %s failed", chat_id)
                failed += 1
            await asyncio.sleep(PACE_SECONDS)
        report = texts.BROADCAST_RESULT.format(
            sent=sent,
            blocked=blocked,
            failed=failed,
            total=len(targets),
            seconds=int(time.monotonic() - started),
        )
    except Exception:
        logger.exception("broadcast crashed")
        report = texts.BROADCAST_CRASHED
    finally:
        release()
    try:
        await bot.send_message(owner_id, report)
    except Exception:
        logger.exception("could not deliver the broadcast report")


def start_background(coro: Awaitable[None]) -> asyncio.Task:
    task = asyncio.create_task(coro)  # type: ignore[arg-type]
    _tasks.add(task)
    task.add_done_callback(_tasks.discard)
    return task
