"""Observer sub-admins (ناظر): frozen out of every automatic billing path.

Marking one must record the exemption, void what they already owe, and leave
no path — Friday settlement, the usage sync, the wallet drawdown or any
reminder — able to invoice or chase them again. The freeze must be a freeze,
not a soft limit: the weekly baseline and the sync ledger are deliberately left
stale so un-marking bills the whole gap in one catch-up instead of quietly
losing it.
"""

import asyncio
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from backend.bot import billing, db, texts, usage_sync, weekly
from backend.db import crud
from backend.db.model import Admins, MarzbanUsers, Panels

TEHRAN = ZoneInfo("Asia/Tehran")
GB = 1024**3
NOW = datetime(2026, 10, 16, 8, 0, tzinfo=TEHRAN)
STAMP = "2026-42"
WEEK_START = datetime(2026, 10, 10, 0, 0, tzinfo=TEHRAN)
# Long past: any clock agrees it is overdue.
PAST_DUE = "2000-01-01T00:00:00+00:00"


class FakeBot:
    def __init__(self):
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


@pytest.fixture()
def admin(db_session):
    def make(username="fuad", telegram_id=7531278023, panel="touch", traffic=100 * GB):
        row = Admins(
            username=username,
            hashed_password="x",
            telegram_id=telegram_id,
            panel=panel,
            is_active=True,
            traffic=traffic,
        )
        db_session.add(row)
        db_session.commit()
        return row

    return make


@pytest.fixture()
def priced(ledger):
    ledger.set_setting("price_per_gb", "2900.0")
    return ledger


# --- membership ---------------------------------------------------------------

def test_mark_records_membership_and_is_idempotent(ledger):
    assert ledger.list_observer_admins() == []

    first = ledger.mark_observer_admin("fuad", marked_by=42)
    second = ledger.mark_observer_admin("fuad", marked_by=42)

    assert first == {"added": True, "invoices_cancelled": 0, "debt_cleared": 0}
    assert second == {"added": False, "invoices_cancelled": 0, "debt_cleared": 0}
    assert ledger.is_observer_admin("fuad")
    assert ledger.list_observer_admins() == ["fuad"]

    assert ledger.unmark_observer_admin("fuad") is True
    assert ledger.unmark_observer_admin("fuad") is False
    assert not ledger.is_observer_admin("fuad")


def test_mark_voids_only_this_owners_obligations(ledger):
    panel_invoice = db.create_invoice(
        telegram_id=111, amount=5000, description="x", due_at=None,
        admin_username="fuad",
    )
    hand_invoice = db.create_invoice(
        telegram_id=111, amount=700, description="hand", due_at=None,
    )
    other_invoice = db.create_invoice(
        telegram_id=222, amount=900, description="y", due_at=None,
        admin_username="other",
    )
    paid_invoice = db.create_invoice(
        telegram_id=111, amount=100, description="p", due_at=None,
        admin_username="fuad",
    )
    db.mark_invoice_paid(paid_invoice)
    db.add_debt("fuad", 111, 6000)
    db.mark_overdue("fuad")

    result = db.mark_observer_admin("fuad", marked_by=1, telegram_id=111)

    assert result == {"added": True, "invoices_cancelled": 2, "debt_cleared": 6000}
    assert db.get_invoice(panel_invoice).status == "cancelled"
    # Raised by hand against the same person: no admin_username to match on.
    assert db.get_invoice(hand_invoice).status == "cancelled"
    assert db.get_invoice(other_invoice).status == "pending"
    assert db.get_invoice(paid_invoice).status == "paid"
    assert db.get_debt("fuad") == 0
    record = db.get_debt_record("fuad")
    assert record["overdue_since"] is None
    assert record["last_warned_at"] is None


# --- reminders ----------------------------------------------------------------

def test_observers_are_never_chased(ledger):
    # A debt accrued *after* the mark (a deliberate purchase) must still not
    # be chased: the exemption is about the person, not the snapshot.
    db.add_debt("fuad", 111, 6000)
    db.add_debt("other", 222, 3000)
    db.mark_overdue("fuad")
    db.mark_overdue("other")
    db.mark_observer_admin("fuad", marked_by=1)
    db.add_debt("fuad", 111, 6000)
    db.mark_overdue("fuad")

    bot = FakeBot()
    sent = asyncio.run(weekly.send_reminders(bot))
    assert sent == 1
    assert {chat for chat, _ in bot.messages} == {222}

    bot = FakeBot()
    sent = asyncio.run(weekly.send_overdue_reminders(bot))
    assert sent == 1
    assert {chat for chat, _ in bot.messages} == {222}


def test_observer_invoices_are_not_chased_and_not_stamped(ledger):
    db.mark_observer_admin("fuad", marked_by=1)
    # Raised after the mark (a deliberate hand invoice): still never chased.
    fuad_invoice = db.create_invoice(
        telegram_id=111, amount=100, description="x", due_at=PAST_DUE,
        admin_username="fuad",
    )
    other_invoice = db.create_invoice(
        telegram_id=222, amount=100, description="y", due_at=PAST_DUE,
        admin_username="other",
    )

    bot = FakeBot()
    sent = asyncio.run(weekly.send_invoice_reminders(bot))

    assert sent == 1
    assert {chat for chat, _ in bot.messages} == {222}
    # Not stamped either: un-marking must resume the chase, not skip the day.
    assert db.get_invoice(fuad_invoice).status == "pending"
    assert db.get_invoice(fuad_invoice).last_reminded_date is None
    assert db.get_invoice(other_invoice).last_reminded_date is not None


def test_friday_settlement_leaves_observer_debts_untouched(ledger):
    db.mark_observer_admin("fuad", marked_by=1)
    db.add_debt("fuad", 111, 6000)
    db.mark_overdue("fuad")
    db.add_debt("other", 222, 3000)
    db.mark_overdue("other")

    bot = FakeBot()
    asyncio.run(weekly.run_settlement(bot))

    assert db.get_debt("fuad") == 6000
    assert 111 not in {chat for chat, _ in bot.messages}  # no debtor DM
    # Control: a normal debtor is told where they stand, so the skip is the
    # observer's and not the whole phase silently not running.
    assert db.get_debt("other") == 3000
    assert 222 in {chat for chat, _ in bot.messages}


# --- weekly consumption settlement --------------------------------------------

def test_settlement_freezes_observer_then_catches_up_after_unmark(
    ledger, priced, admin, db_session, monkeypatch
):
    db_session.add(
        Panels(
            panel_type="marzban",
            name="touch",
            url="http://marzban.test:8000",
            username="sudo",
            password="x",
        )
    )
    db_session.commit()
    admin(panel="touch")  # fuad, consumption, observed
    admin(username="other", telegram_id=999, panel="touch")  # consumption
    ledger.set_weekly_mode("fuad", "consumption")
    ledger.set_weekly_mode("other", "consumption")
    ledger.set_created_volume_baseline("fuad", "2026-41", 100 * GB)
    ledger.set_created_volume_baseline("other", "2026-41", 10 * GB)
    ledger.mark_observer_admin("fuad", marked_by=1)

    async def fake_read(panel):
        return [
            {"username": "u1", "data_limit": 250 * GB, "admin": {"username": "fuad"}},
            {"username": "u2", "data_limit": 50 * GB, "admin": {"username": "fuad"}},
            {"username": "u3", "data_limit": 40 * GB, "admin": {"username": "other"}},
        ]

    monkeypatch.setattr(weekly, "_read_panel_with_retry", fake_read)
    bot = FakeBot()

    invoice_lines, warning_lines = asyncio.run(
        weekly._settle_consumption(bot, NOW, STAMP)
    )

    assert not ledger.consumption_invoice_exists("fuad", STAMP)
    assert ledger.consumption_invoice_exists("other", STAMP)
    assert warning_lines == []
    # Frozen meter: old stamp, old figure — nothing of the gap is written off.
    baseline = ledger.get_created_volume_baseline("fuad")
    assert baseline["week_stamp"] == "2026-41"
    assert baseline["total_bytes"] == 100 * GB
    assert any("fuad" in line and "ناظر" in line for line in invoice_lines)

    # Un-mark: the whole frozen gap (350 - 100 GB) is billed in one invoice.
    ledger.unmark_observer_admin("fuad")
    now_two = datetime(2026, 10, 23, 8, 0, tzinfo=TEHRAN)

    async def bigger_read(panel):
        return [
            {"username": "u1", "data_limit": 300 * GB, "admin": {"username": "fuad"}},
            {"username": "u2", "data_limit": 50 * GB, "admin": {"username": "fuad"}},
            {"username": "u3", "data_limit": 40 * GB, "admin": {"username": "other"}},
        ]

    monkeypatch.setattr(weekly, "_read_panel_with_retry", bigger_read)
    asyncio.run(weekly._settle_consumption(bot, now_two, "2026-43"))

    assert ledger.consumption_invoice_exists("fuad", "2026-43")
    fuad_invoices = [
        i for i in (db.get_invoice(n) for n in range(1, 10))
        if i and i.admin_username == "fuad"
    ]
    assert len(fuad_invoices) == 1
    assert fuad_invoices[0].amount == round(250 * 2900)


# --- wallet drawdown ----------------------------------------------------------

def test_wallet_drawdown_skips_observer_debts(ledger):
    db.add_debt("fuad", 111, 6000)
    db.add_debt("other", 111, 3000)
    db.add_wallet_balance(111, 10000)

    results = billing.apply_wallet_to_debts(111, skip_usernames={"fuad"})

    assert [r["username"] for r in results] == ["other"]
    assert db.get_debt("fuad") == 6000
    assert db.get_debt("other") == 0
    assert db.get_wallet_balance(111) == 7000


# --- usage sync ---------------------------------------------------------------

def test_usage_sync_skips_observer_and_still_charges_the_rest(
    ledger, priced, admin, db_session, monkeypatch
):
    admin(username="fuad", telegram_id=111, traffic=100 * GB)
    admin(username="other", telegram_id=222, traffic=10 * GB)
    db_session.add(
        MarzbanUsers(username="known-f", owner="fuad", data_limit=10 * GB, source="baseline")
    )
    db_session.add(
        MarzbanUsers(username="known-o", owner="other", data_limit=10 * GB, source="baseline")
    )
    db_session.commit()
    db.mark_observer_admin("fuad", marked_by=1)

    def fake_read(panel):
        return [
            {"username": "known-f", "data_limit": 10 * GB, "admin": {"username": "fuad"}},
            {"username": "new-f", "data_limit": 20 * GB, "admin": {"username": "fuad"}},
            {"username": "known-o", "data_limit": 10 * GB, "admin": {"username": "other"}},
            {"username": "new-o", "data_limit": 20 * GB, "admin": {"username": "other"}},
        ]

    monkeypatch.setattr(usage_sync, "_read_panel_users", fake_read)
    panel = SimpleNamespace(name="touch", username="sudo")
    ledger_all = crud.get_marzban_users_grouped(db_session)

    lines = usage_sync._sync_panel(db_session, panel, ledger_all, {"fuad"})

    assert any("fuad" in line and "ناظر" in line for line in lines)
    assert any("other" in line for line in lines)
    # Frozen: no traffic drawdown for the observer, however many users appear.
    assert int(admin_row(db_session, "fuad").traffic or 0) == 100 * GB
    # The other owner is charged normally: 10 GB - 20 GB = -10 GB of debt.
    assert int(admin_row(db_session, "other").traffic or 0) == -10 * GB
    invoiced = {i.admin_username for i in db.list_pending_invoices()}
    assert "fuad" not in invoiced
    assert "other" in invoiced


def admin_row(db_session, username: str):
    db_session.expire_all()
    return crud.get_admin_by_username(db_session, username)


# --- bot wiring ---------------------------------------------------------------

def test_observer_buttons_live_in_the_settings_menu():
    from backend.bot import keyboards
    from backend.bot.nav import ALL_MENU_TEXTS

    for label in (texts.BTN_MARK_OBSERVER, texts.BTN_UNMARK_OBSERVER, texts.BTN_LIST_OBSERVERS):
        assert label in ALL_MENU_TEXTS  # or every FSM flow would swallow taps

    rows = [[button.text for button in row] for row in keyboards.settings_section_kb().keyboard]
    flat = [text for row in rows for text in row]
    for label in (texts.BTN_MARK_OBSERVER, texts.BTN_UNMARK_OBSERVER, texts.BTN_LIST_OBSERVERS):
        assert label in flat
    assert rows[-1] == [texts.BTN_BACK]  # Back still ends the section alone
