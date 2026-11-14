"""The main bot task must not be able to die silently.

`start_bot()` holds the task in a module global, so asyncio never reports
"exception was never retrieved" — an unsupervised crash would take the bot
down with zero log lines and receipts would quietly stop arriving. It is now
wrapped in the same supervisor as the background loops: the crash is logged
with its traceback and the bot comes back on its own.
"""

import asyncio
import contextlib
import logging

import pytest

from backend.bot import service


@pytest.fixture(autouse=True)
def _fast_restart(monkeypatch):
    monkeypatch.setattr(service, "SUPERVISOR_RESTART_DELAY", 0.05)


def test_a_crashed_bot_task_is_logged_and_restarted(caplog):
    calls = []

    async def flaky():
        calls.append(1)
        if len(calls) == 1:
            raise RuntimeError("boom")
        await asyncio.sleep(3600)

    async def scenario():
        task = asyncio.create_task(service._supervised("telegram_bot", flaky))
        await asyncio.sleep(0.4)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert len(calls) >= 2, "the supervisor did not restart the bot task"
    assert any(
        "telegram_bot" in record.message and "boom" in record.message
        for record in caplog.records
    )


def test_a_clean_exit_is_reported_too(caplog):
    async def quitter():
        return None

    async def scenario():
        task = asyncio.create_task(service._supervised("telegram_bot", quitter))
        await asyncio.sleep(0.4)
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task

    asyncio.run(scenario())

    assert any(
        "telegram_bot" in record.message and "exited" in record.message
        for record in caplog.records
    )


def test_stop_bot_cancels_whatever_is_running():
    started = asyncio.Event()

    async def runner():
        started.set()
        await asyncio.sleep(3600)

    async def scenario():
        service._bot_task = asyncio.create_task(service._supervised("telegram_bot", runner))
        await started.wait()
        await service.stop_bot()
        return service.is_running()

    assert asyncio.run(scenario()) is False
    assert service._bot_task is None


def test_routers_survive_a_restart_after_their_dispatcher_died():
    """A restarted bot task must be able to re-attach the module routers.

    The routers are module-level singletons, so after any attempt dies they
    still point at its dispatcher — and aiogram refuses a second attach. This
    is exactly what production logged ('Router is already attached') on every
    container restart: the supervisor restarted the task and the restart died
    on attach, leaving the bot dark. Detach-then-attach must let the routers
    live through any number of restarts.
    """
    from aiogram import Dispatcher
    from aiogram.fsm.storage.memory import MemoryStorage

    from backend.bot.routers import all_routers

    try:
        dp_one = Dispatcher(storage=MemoryStorage())
        service._attach_routers(dp_one, all_routers)
        assert all_routers[0].parent_router is dp_one

        dp_two = Dispatcher(storage=MemoryStorage())
        service._attach_routers(dp_two, all_routers)
        assert all_routers[0].parent_router is dp_two

        dp_three = Dispatcher(storage=MemoryStorage())
        service._attach_routers(dp_three, all_routers)
        assert all_routers[0].parent_router is dp_three
        assert all_routers[-1].parent_router is dp_three
    finally:
        # Leave the module state pristine for every other test.
        for router in all_routers:
            router._parent_router = None
