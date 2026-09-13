"""Bot lifecycle manager — starts the Telegram bot as a background task
within the FastAPI process.

The bot is disabled when BOT_TOKEN is empty, which is the default for
existing installations that haven't configured the top-up bot yet.
"""

from __future__ import annotations

import asyncio
import logging

from backend.bot.config import bot_config

logger = logging.getLogger(__name__)

_bot_task: asyncio.Task | None = None


async def _run_bot() -> None:
    """Entry point for the bot background task."""
    from aiogram import Bot, Dispatcher
    from aiogram.client.default import DefaultBotProperties
    from aiogram.enums import ParseMode
    from aiogram.fsm.storage.memory import MemoryStorage

    from backend.bot import db
    from backend.bot.middlewares import ForceJoinMiddleware
    from backend.bot.routers import all_routers
    from backend.bot.backups import run_backup_scheduler
    from backend.bot.forecast import run_forecast_scheduler
    from backend.bot.warnings import run_warning_scanner
    from backend.bot.weekly import run_weekly_scheduler

    if not bot_config.bot_token:
        return

    logger.info("Starting Telegram top-up bot...")
    db.init_db()

    bot = Bot(
        token=bot_config.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dp = Dispatcher(storage=MemoryStorage())
    force_join = ForceJoinMiddleware()
    dp.message.outer_middleware(force_join)
    dp.callback_query.outer_middleware(force_join)
    for router in all_routers:
        dp.include_router(router)

    logger.info("Bot polling starting")
    await bot.delete_webhook(drop_pending_updates=True)

    background = [
        asyncio.create_task(run_warning_scanner(bot)),
        asyncio.create_task(run_weekly_scheduler(bot)),
        asyncio.create_task(run_backup_scheduler(bot)),
        asyncio.create_task(run_forecast_scheduler(bot)),
    ]
    try:
        await dp.start_polling(bot)
    finally:
        for task in background:
            task.cancel()
        await bot.session.close()
        logger.info("Bot polling stopped")


def start_bot() -> None:
    """Create the asyncio task (called from FastAPI startup)."""
    global _bot_task
    if not bot_config.bot_token:
        logger.info("BOT_TOKEN not set — top-up bot disabled")
        return
    _bot_task = asyncio.create_task(_run_bot())
    logger.info("Top-up bot task created")


async def stop_bot() -> None:
    """Gracefully stop the bot (called from FastAPI shutdown)."""
    global _bot_task
    if _bot_task and not _bot_task.done():
        _bot_task.cancel()
        try:
            await _bot_task
        except asyncio.CancelledError:
            pass
        _bot_task = None
        logger.info("Top-up bot stopped")
