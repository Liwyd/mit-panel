"""Superadmin: cut off a late-paying sub-admin's users, and turn them back on.

The work itself lives in backend.bot.suspend; this is only the buttons. A run
can touch thousands of users, so it goes on in the background and edits one
message with its progress instead of holding the handler open.
"""

from __future__ import annotations

import asyncio
import html
from datetime import datetime

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from backend.bot import db, keyboards, suspend, texts
from backend.bot.filters import SuperadminFilter
from backend.bot.nav import remember_section, superadmin_kb
from backend.db import crud, engin
from backend.utils.logger import logger

router = Router(name="suspend")
router.message.filter(SuperadminFilter())
router.callback_query.filter(SuperadminFilter())

# Running jobs, kept so the event loop does not drop them half-way.
_jobs: set[asyncio.Task] = set()


def _spawn(coro) -> None:
    task = asyncio.create_task(coro)
    _jobs.add(task)
    task.add_done_callback(_jobs.discard)


def _when(stamp: str | None) -> str:
    try:
        return datetime.fromisoformat(stamp or "").strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return stamp or "—"


async def _safe_edit(message: Message, text: str, **kwargs) -> None:
    try:
        await message.edit_text(text, **kwargs)
    except Exception:
        pass  # "message is not modified", or it was deleted


async def _notify(bot: Bot, telegram_id: int | None, text: str) -> None:
    if not telegram_id:
        return
    try:
        await bot.send_message(int(telegram_id), text)
    except Exception:
        pass


# ------------------------------------------------------------------ suspend


@router.message(F.text == texts.BTN_SUSPEND_ADMIN)
async def start_suspend(message: Message, state: FSMContext) -> None:
    remember_section(message.from_user.id, "finance")
    await state.clear()
    admins = suspend.suspendable_admins()
    if not admins:
        await message.answer(texts.NO_ADMINS_TO_SUSPEND, reply_markup=superadmin_kb(message.from_user.id))
        return
    await message.answer(
        texts.ASK_PICK_ADMIN_TO_SUSPEND, reply_markup=keyboards.admin_picker_kb(admins, "susp")
    )


@router.callback_query(F.data.startswith("suspcust:"))
async def suspend_from_debt_card(call: CallbackQuery) -> None:
    """«⛔ قطع کاربران» on an overdue customer's card: their panels."""
    telegram_id = int(call.data.split(":", 1)[1])
    supported = {a.id for a in suspend.suspendable_admins()}
    with engin.sessionLocal() as session:
        admins = [a for a in crud.get_admins_by_telegram_id(session, telegram_id) if a.id in supported]
    if not admins:
        await call.answer(texts.NO_ADMINS_TO_SUSPEND, show_alert=True)
        return
    await call.answer()
    if len(admins) == 1:
        await _ask_confirm(call.message, admins[0].id, edit=False)
        return
    await call.message.answer(
        texts.ASK_PICK_ADMIN_TO_SUSPEND, reply_markup=keyboards.admin_picker_kb(admins, "susp")
    )


@router.callback_query(F.data.startswith("susp:"))
async def picked_admin_to_suspend(call: CallbackQuery) -> None:
    await call.answer()
    await _ask_confirm(call.message, int(call.data.split(":", 1)[1]), edit=True)


async def _ask_confirm(message: Message, admin_id: int, *, edit: bool) -> None:
    """Count the active users first: the superadmin should know how many
    people are about to lose their connection before saying yes."""
    with engin.sessionLocal() as session:
        admin = crud.get_admin_by_id(session, admin_id)
        username = admin.username if admin else ""
    if not username:
        await message.answer(texts.SUSPEND_FAILED.format(username="—", error="ساب‌ادمین پیدا نشد"))
        return
    name = html.escape(username)
    counting = texts.SUSPEND_COUNTING.format(username=name)
    if edit:
        await _safe_edit(message, counting)
        target_msg = message
    else:
        target_msg = await message.answer(counting)
    try:
        target = suspend.load_target(username)
        users = await suspend.active_users(target)
    except suspend.SuspendError as exc:
        await _safe_edit(target_msg, texts.SUSPEND_FAILED.format(username=name, error=html.escape(str(exc))))
        return
    if not users:
        await _safe_edit(target_msg, texts.SUSPEND_NOTHING.format(username=name))
        return
    await _safe_edit(
        target_msg,
        texts.CONFIRM_SUSPEND.format(
            username=name, panel=html.escape(target.panel_name), count=len(users)
        ),
        reply_markup=keyboards.confirm_suspend_kb(admin_id),
    )


@router.callback_query(F.data == "susp_no")
async def cancel_suspend(call: CallbackQuery) -> None:
    await call.answer()
    await _safe_edit(call.message, texts.SUSPEND_CANCELLED)


@router.callback_query(F.data.startswith("suspok:"))
async def confirm_suspend(call: CallbackQuery, bot: Bot) -> None:
    admin_id = int(call.data.split(":", 1)[1])
    with engin.sessionLocal() as session:
        admin = crud.get_admin_by_id(session, admin_id)
        username = admin.username if admin else ""
        telegram_id = admin.telegram_id if admin else None
    if not username:
        await call.answer("این ساب‌ادمین دیگر وجود ندارد", show_alert=True)
        return
    await call.answer()
    name = html.escape(username)
    # The buttons go at once, so a second tap cannot start a second run.
    await _safe_edit(call.message, texts.SUSPEND_RUNNING.format(username=name, done=0, total="…"))
    _spawn(_run_suspend(call.message, bot, username, telegram_id, call.from_user.id))


async def _run_suspend(message: Message, bot: Bot, username: str, telegram_id, by: int) -> None:
    name = html.escape(username)

    async def progress(done: int, total: int) -> None:
        await _safe_edit(message, texts.SUSPEND_RUNNING.format(username=name, done=done, total=total))

    try:
        result = await suspend.suspend_admin(username, by=by, progress=progress)
    except suspend.SuspendError as exc:
        await _safe_edit(message, texts.SUSPEND_FAILED.format(username=name, error=html.escape(str(exc))))
        return
    except Exception as exc:
        logger.exception("suspending %s failed", username)
        await _safe_edit(message, texts.SUSPEND_FAILED.format(username=name, error=html.escape(str(exc))))
        return
    if result.total == 0:
        await _safe_edit(message, texts.SUSPEND_NOTHING.format(username=name))
        return
    await _safe_edit(message, texts.SUSPEND_DONE.format(username=name, done=result.done, failed=result.failed))
    if result.done:
        await _notify(bot, telegram_id, texts.SUSPEND_ADMIN_NOTICE.format(username=name))


# ------------------------------------------------------------------ unsuspend


@router.message(F.text == texts.BTN_UNSUSPEND_ADMIN)
async def start_unsuspend(message: Message, state: FSMContext) -> None:
    remember_section(message.from_user.id, "finance")
    await state.clear()
    rows = db.list_suspensions()
    if not rows:
        await message.answer(texts.NO_SUSPENDED_ADMINS, reply_markup=superadmin_kb(message.from_user.id))
        return
    await message.answer(
        texts.ASK_PICK_ADMIN_TO_UNSUSPEND, reply_markup=keyboards.suspended_admins_kb(rows)
    )


@router.callback_query(F.data.startswith("unsusp:"))
async def picked_admin_to_unsuspend(call: CallbackQuery) -> None:
    username = call.data.split(":", 1)[1]
    row = db.get_suspension(username)
    if row is None:
        await call.answer(texts.NO_SUSPENDED_ADMINS, show_alert=True)
        return
    await call.answer()
    await _safe_edit(
        call.message,
        texts.CONFIRM_UNSUSPEND.format(
            username=html.escape(username),
            when=_when(row.get("suspended_at")),
            count=len(db.pending_suspended_users(username)),
        ),
        reply_markup=keyboards.confirm_unsuspend_kb(username),
    )


@router.callback_query(F.data.startswith("unsuspok:"))
async def confirm_unsuspend(call: CallbackQuery, bot: Bot) -> None:
    username = call.data.split(":", 1)[1]
    row = db.get_suspension(username)
    if row is None:
        await call.answer(texts.NO_SUSPENDED_ADMINS, show_alert=True)
        return
    await call.answer()
    name = html.escape(username)
    await _safe_edit(call.message, texts.UNSUSPEND_RUNNING.format(username=name, done=0, total="…"))
    _spawn(_run_unsuspend(call.message, bot, username, row.get("telegram_id")))


async def _run_unsuspend(message: Message, bot: Bot, username: str, telegram_id) -> None:
    name = html.escape(username)

    async def progress(done: int, total: int) -> None:
        await _safe_edit(message, texts.UNSUSPEND_RUNNING.format(username=name, done=done, total=total))

    try:
        result = await suspend.unsuspend_admin(username, progress=progress)
    except Exception as exc:
        if not isinstance(exc, suspend.SuspendError):
            logger.exception("unsuspending %s failed", username)
        await _safe_edit(message, texts.UNSUSPEND_FAILED.format(username=name, error=html.escape(str(exc))))
        return
    text = texts.UNSUSPEND_DONE.format(
        username=name, done=result.done, skipped=result.skipped, failed=result.failed
    )
    if result.failed:
        text += texts.UNSUSPEND_PARTIAL
    await _safe_edit(message, text)
    if result.done:
        await _notify(bot, telegram_id, texts.UNSUSPEND_ADMIN_NOTICE.format(username=name))
