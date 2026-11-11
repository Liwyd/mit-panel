"""A photo that matches no flow used to vanish silently.

Customers pay first and send the receipt afterwards — when the flow's state
is gone (bot restarted mid-flow, receipt sent before the flow was started)
the photo matched no handler and nobody ever learned about it. The customer
believed the receipt was delivered; the superadmin waited for a request that
did not exist (production, 2026-11-11, user id 1131519306). Now the photo
gets an explicit reply pointing at the right flow.

Registered last on purpose: it must only ever see what no earlier handler
wanted. Superadmins are skipped — they forward photos around and never need
the guidance — and groups are left to the chat they live in.
"""

from __future__ import annotations

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from backend.bot import texts
from backend.bot.config import bot_config as settings
from backend.bot.nav import menu_kb_for

router = Router(name="photo_fallback")


@router.message(F.photo, F.chat.type == "private")
async def stray_photo(message: Message, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if message.from_user.id in settings.superadmin_id_list:
        return
    in_flow = await state.get_state() is not None
    await message.answer(
        texts.STRAY_PHOTO_MISPLACED if in_flow else texts.STRAY_PHOTO_GUIDANCE,
        reply_markup=await menu_kb_for(message.from_user.id),
    )
