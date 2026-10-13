"""Friday settlement bills the panel's own created-volume figure.

The old implementation compared the first and last *snapshot* of the week, so
every Saturday creation was already baked into the first snapshot and every
Friday-evening creation fell after the last one — a whole day of each Persian
week was billed to nobody (measured on production: 10 GB invoiced where the
panel showed 45 GB created). Settlement now reads the live figure and invoices
its growth since the previous settlement, so these tests pin down: growth is
billed exactly, shrinkage never is, an owner is billed once per week, and the
first settlement after the switch recovers only what the ledger saw created
this week — never retroactively.
"""

import asyncio
import sqlite3
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend.bot import db, weekly
from backend.db.model import Admins, MarzbanUsers, Panels

TEHRAN = ZoneInfo("Asia/Tehran")
GB = 1024**3
# Friday 08:00 Tehran, the settlement moment; its Persian week starts
# Saturday 2026-10-10.
NOW = datetime(2026, 10, 16, 8, 0, tzinfo=TEHRAN)
STAMP = "2026-42"
WEEK_START = datetime(2026, 10, 10, 0, 0, tzinfo=TEHRAN)
_PANEL = SimpleNamespace(name="touch", panel_type="marzban")


class FakeBot:
    def __init__(self):
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


@pytest.fixture()
def admin(db_session):
    def make(username="fuad", telegram_id=7531278023, panel="touch"):
        row = Admins(
            username=username,
            hashed_password="x",
            telegram_id=telegram_id,
            panel=panel,
            is_active=True,
        )
        db_session.add(row)
        db_session.commit()
        return row

    return make


@pytest.fixture()
def priced(ledger):
    ledger.set_setting("price_per_gb", "2900.0")
    return ledger


def _settle(ledger, bot, admin_row, live_total, stamp=STAMP):
    return asyncio.run(
        weekly._settle_owner(
            bot,
            owner=admin_row.username,
            admin=admin_row,
            live_total=live_total,
            week_start=WEEK_START,
            now=NOW,
            stamp=stamp,
        )
    )


def test_growth_since_last_settlement_is_invoiced(ledger, priced, admin):
    owner = admin()
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)
    bot = FakeBot()

    lines = _settle(ledger, bot, owner, 300 * GB)

    invoices = [i for i in [db.get_invoice(n) for n in range(1, 5)] if i]
    assert len(invoices) == 1
    invoice = invoices[0]
    assert invoice.amount == round(200 * 2900)
    assert invoice.admin_username == "fuad"
    assert "(200.0 GB)" in invoice.description
    assert STAMP in invoice.description
    assert invoice.traffic_gb == 0  # paying it must credit no GB
    assert db.consumption_invoice_exists("fuad", STAMP)

    baseline = ledger.get_created_volume_baseline("fuad")
    assert baseline["week_stamp"] == STAMP
    assert baseline["total_bytes"] == 300 * GB
    assert bot.messages and bot.messages[0][0] == 7531278023
    assert len(lines) == 1  # the superadmin report line


def test_a_shrunk_panel_is_never_billed_and_resets_its_baseline(
    ledger, priced, admin
):
    owner = admin()
    ledger.set_created_volume_baseline("fuad", "2026-41", 300 * GB)
    bot = FakeBot()

    _settle(ledger, bot, owner, 50 * GB)

    assert not db.consumption_invoice_exists("fuad", STAMP)
    baseline = ledger.get_created_volume_baseline("fuad")
    assert baseline["total_bytes"] == 50 * GB  # next week grows from here
    assert not bot.messages


def test_unchanged_panel_updates_only_the_week_stamp(ledger, priced, admin):
    owner = admin()
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)
    bot = FakeBot()

    _settle(ledger, bot, owner, 100 * GB)

    assert not db.consumption_invoice_exists("fuad", STAMP)
    assert ledger.get_created_volume_baseline("fuad")["week_stamp"] == STAMP


def test_a_second_run_same_week_is_a_no_op(ledger, priced, admin):
    owner = admin()
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)
    bot = FakeBot()

    _settle(ledger, bot, owner, 300 * GB)
    _settle(ledger, bot, owner, 300 * GB)

    assert db.consumption_invoice_exists("fuad", STAMP)
    assert not db.consumption_invoice_exists("fuad", "2026-43")
    # One invoice only: the second run saw the baseline already stamped.
    with sqlite3.connect(ledger.bot_config.sqlite_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM invoices WHERE admin_username = 'fuad'"
        ).fetchone()[0]
    assert count == 1


def test_a_crash_after_the_invoice_does_not_duplicate_it(ledger, priced, admin):
    """Baseline write lost between invoice and baseline: re-run re-computes
    the same delta, finds the invoice, and only advances the baseline."""
    owner = admin()
    bot = FakeBot()
    db.create_invoice(
        telegram_id=7531278023,
        amount=580000,
        description="مصرف هفتگی پنل fuad — 2026-42 (200.0 GB)",
        due_at=None,
        admin_username="fuad",
        week_stamp=STAMP,
    )

    lines = _settle(ledger, bot, owner, 300 * GB)

    assert lines == []  # no second superadmin line
    assert not bot.messages
    baseline = ledger.get_created_volume_baseline("fuad")
    assert baseline["week_stamp"] == STAMP
    with sqlite3.connect(ledger.bot_config.sqlite_path) as conn:
        count = conn.execute(
            "SELECT COUNT(*) FROM invoices WHERE admin_username = 'fuad'"
        ).fetchone()[0]
    assert count == 1


def test_an_unpriced_owner_is_carried_forward_not_silently_dropped(
    ledger, admin
):
    owner = admin()
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)
    bot = FakeBot()

    lines = _settle(ledger, bot, owner, 300 * GB)

    assert len(lines) == 1
    assert "200.0" in lines[0]
    assert not db.consumption_invoice_exists("fuad", STAMP)
    # Held back so next week's delta still contains this week's growth.
    assert ledger.get_created_volume_baseline("fuad")["week_stamp"] == "2026-41"


def test_a_missing_telegram_id_is_carried_forward(ledger, priced, db_session):
    owner = Admins(
        username="fuad",
        hashed_password="x",
        telegram_id=None,
        panel="touch",
        is_active=True,
    )
    db_session.add(owner)
    db_session.commit()
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)

    lines = _settle(ledger, FakeBot(), owner, 300 * GB)

    assert len(lines) == 1
    assert ledger.get_created_volume_baseline("fuad")["week_stamp"] == "2026-41"


def test_first_settlement_bills_only_this_weeks_ledger_creations(
    ledger, priced, admin, db_session
):
    """The switch-over week: creations the mirror saw during this Persian week
    (a Saturday one included) are recovered exactly; anything older is never
    billed retroactively. From the next week the live baseline takes over."""
    owner = admin()
    db_session.add(
        MarzbanUsers(
            username="saturday-new",
            owner="fuad",
            data_limit=100 * GB,
            source="bot",
            # Saturday 2026-10-12 10:00 Tehran — the day the old snapshot
            # math always lost.
            created_at=datetime(2026, 10, 12, 6, 30),
        )
    )
    db_session.add(
        MarzbanUsers(
            username="last-week",
            owner="fuad",
            data_limit=250 * GB,
            source="bot",
            created_at=datetime(2026, 10, 2, 12, 0),  # before the window
        )
    )
    db_session.commit()
    bot = FakeBot()

    lines = _settle(ledger, bot, owner, 350 * GB)

    invoices = [db.get_invoice(1)]
    assert invoices[0].amount == round(100 * 2900)
    baseline = ledger.get_created_volume_baseline("fuad")
    assert baseline["total_bytes"] == 350 * GB  # live figure adopted


def test_consumption_invoice_uniqueness_is_enforced(ledger, priced):
    db.create_invoice(
        telegram_id=1, amount=100, description="x", due_at=None,
        admin_username="fuad", week_stamp=STAMP,
    )
    with pytest.raises(sqlite3.IntegrityError):
        db.create_invoice(
            telegram_id=1, amount=100, description="y", due_at=None,
            admin_username="fuad", week_stamp=STAMP,
        )
    # A different week, or a panel-less invoice, is unaffected.
    db.create_invoice(
        telegram_id=1, amount=100, description="x", due_at=None,
        admin_username="fuad", week_stamp="2026-43",
    )
    db.create_invoice(telegram_id=1, amount=100, description="hand", due_at=None)


def test_idempotency_match_is_exact_not_a_substring(ledger):
    db.create_invoice(
        telegram_id=1, amount=100, description="x", due_at=None,
        admin_username="fuad", week_stamp="2026-41",
    )
    assert db.consumption_invoice_exists("fuad", "2026-41")
    assert not db.consumption_invoice_exists("fuadx", "2026-41")
    assert not db.consumption_invoice_exists("fuad", "2026-42")


def _touch_panel(db_session, username="sudo"):
    db_session.add(
        Panels(
            panel_type="marzban",
            name="touch",
            url="http://marzban.test:8000",
            username=username,
            password="x",
        )
    )
    db_session.commit()


def test_settlement_end_to_end_bills_growth_and_only_consumption_owners(
    ledger, priced, admin, db_session, monkeypatch
):
    _touch_panel(db_session)
    admin(panel="touch")  # fuad, consumption
    other = admin(username="other", telegram_id=999, panel="touch")
    db_session.commit()
    ledger.set_weekly_mode("fuad", "consumption")  # other stays delayed
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)
    ledger.set_created_volume_baseline("other", "2026-41", 10 * GB)

    async def fake_read(panel):
        return [
            {"username": "u1", "data_limit": 250 * GB, "admin": {"username": "fuad"}},
            {"username": "u2", "data_limit": 50 * GB, "admin": {"username": "fuad"}},
            {"username": "u3", "data_limit": 40 * GB, "admin": {"username": "other"}},
            {"username": "svc", "data_limit": 9 * GB, "admin": {"username": "sudo"}},
            {"username": "own", "data_limit": 5 * GB, "admin": None},
        ]

    monkeypatch.setattr(weekly, "_read_panel_with_retry", fake_read)
    bot = FakeBot()

    invoice_lines, warning_lines = asyncio.run(
        weekly._settle_consumption(bot, NOW, STAMP)
    )

    assert db.consumption_invoice_exists("fuad", STAMP)
    assert not db.consumption_invoice_exists("other", STAMP)  # delayed mode
    assert db.get_invoice(1).amount == round(200 * 2900)
    assert warning_lines == []
    assert len(invoice_lines) == 1
    # The panel's service account and ownerless users bill nobody.
    # The delayed-mode owner's baseline is untouched: their debt flows
    # through the wallet settlement, not the consumption invoice.
    assert ledger.get_created_volume_baseline("other")["total_bytes"] == 10 * GB


def test_an_unreadable_panel_defers_its_owners_whole(
    ledger, priced, admin, db_session, monkeypatch
):
    _touch_panel(db_session)
    admin(panel="touch")
    ledger.set_weekly_mode("fuad", "consumption")
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)

    async def down(panel):
        return None

    monkeypatch.setattr(weekly, "_read_panel_with_retry", down)

    invoice_lines, warning_lines = asyncio.run(
        weekly._settle_consumption(FakeBot(), NOW, STAMP)
    )

    assert invoice_lines == []
    assert len(warning_lines) == 1
    assert "touch" in warning_lines[0]
    # Held, not zeroed: the untouched baseline catches up automatically once
    # the panel is readable again.
    assert ledger.get_created_volume_baseline("fuad")["week_stamp"] == "2026-41"


def test_a_panel_that_reports_no_users_is_treated_as_unreadable(
    ledger, priced, admin, db_session, monkeypatch
):
    _touch_panel(db_session)
    admin(panel="touch")
    ledger.set_weekly_mode("fuad", "consumption")
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)

    async def down(panel):
        return None

    monkeypatch.setattr(weekly, "_read_panel_with_retry", down)

    invoice_lines, warning_lines = asyncio.run(
        weekly._settle_consumption(FakeBot(), NOW, STAMP)
    )
    assert not db.consumption_invoice_exists("fuad", STAMP)
    assert invoice_lines == []
    assert warning_lines
    assert ledger.get_created_volume_baseline("fuad")["week_stamp"] == "2026-41"


def test_stale_weekly_payment_row_is_ignored(ledger, priced):
    """weekly_payment may name a panel that no longer exists (a renamed or
    removed admin); settlement must bill nothing rather than crash."""
    ledger.set_weekly_mode("ghost", "consumption")

    invoice_lines, warning_lines = asyncio.run(
        weekly._settle_consumption(FakeBot(), NOW, STAMP)
    )

    assert invoice_lines == [] and warning_lines == []


def test_panel_read_retries_then_succeeds(monkeypatch):
    monkeypatch.setattr(weekly, "PANEL_READ_BACKOFF", 0.0)
    attempts = []

    def flaky(panel):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("read timeout")
        return [{"username": "u", "data_limit": GB}]

    monkeypatch.setattr(weekly, "_read_panel_users", flaky)
    users = asyncio.run(weekly._read_panel_with_retry(_PANEL))
    assert users and len(attempts) == 3


def test_panel_read_gives_up_returning_none(monkeypatch):
    monkeypatch.setattr(weekly, "PANEL_READ_BACKOFF", 0.0)
    monkeypatch.setattr(weekly, "_read_panel_users", lambda panel: [])
    assert asyncio.run(weekly._read_panel_with_retry(_PANEL)) is None

    def boom(panel):
        raise RuntimeError("down")

    monkeypatch.setattr(weekly, "_read_panel_users", boom)
    assert asyncio.run(weekly._read_panel_with_retry(_PANEL)) is None


def test_week_start_is_saturday_midnight_tehran():
    assert weekly._week_start(NOW) == WEEK_START
    # A Saturday itself is its own week's start.
    saturday = datetime(2026, 10, 10, 15, 0, tzinfo=TEHRAN)
    assert weekly._week_start(saturday) == WEEK_START


def test_supervised_restarts_a_crashed_runner(monkeypatch):
    from backend.bot import service

    monkeypatch.setattr(service, "SUPERVISOR_RESTART_DELAY", 0.001)
    calls = []

    async def crashy():
        calls.append(1)
        if len(calls) >= 2:
            raise asyncio.CancelledError
        raise RuntimeError("boom")

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service._supervised("crashy", crashy))
    assert len(calls) == 2


def test_supervised_restarts_a_normally_returning_runner(monkeypatch):
    from backend.bot import service

    monkeypatch.setattr(service, "SUPERVISOR_RESTART_DELAY", 0.001)
    calls = []

    async def returns():
        calls.append(1)
        if len(calls) >= 2:
            raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(service._supervised("returns", returns))
    assert len(calls) == 2
