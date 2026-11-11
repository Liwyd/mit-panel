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
