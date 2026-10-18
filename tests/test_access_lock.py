"""Access locks: a reseller who owes money loses both MIT Panel and Marzban.

The lock password is written to Marzban first (remote-first) and only then to
MIT Panel's copies, with the exact original password kept in the bot database
so payment restores byte-for-byte what the admin had. These tests pin the
invariants that keep a live panel safe: a failed remote call must change
nothing, a failed local write must compensate the remote change, observers
must never be locked, and everything must be idempotent under re-runs.
"""

import asyncio
from types import SimpleNamespace

import pytest

from backend.auth.hash import verify_password
from backend.bot import access_lock
from backend.bot.access_lock import LOCK_PASSWORD
from backend.db import crud
from backend.db.model import Admins

# Any timestamp comfortably older than the 12-hour grace period.
LONG_AGO = "2000-01-01T00:00:00+00:00"
ORIGINAL_PASSWORD = "orig-secret"


class FakeBot:
    def __init__(self):
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


class FakeMarzban:
    """Stands in for the sudo-authenticated Marzban admin API."""

    calls: list[tuple[str, str]] = []
    status: int = 200
    raise_error: bool = False

    def __init__(self, url, username, password, **kwargs):
        self.url = url
        self.username = username

    async def update_admin_password(self, admin_username, new_password):
        FakeMarzban.calls.append((admin_username, new_password))
        if FakeMarzban.raise_error:
            raise RuntimeError("panel down")
        return FakeMarzban.status

    @classmethod
    def reset(cls):
        cls.calls = []
        cls.status = 200
        cls.raise_error = False


@pytest.fixture()
def fake_marzban(monkeypatch):
    FakeMarzban.reset()
    monkeypatch.setattr(access_lock, "APIService", FakeMarzban)
    monkeypatch.setattr(
        access_lock, "bot_config", SimpleNamespace(superadmin_id_list=[999])
    )
    return FakeMarzban


@pytest.fixture()
def locked_admin(db_session, marzban_panel, ledger, fake_marzban):
    """An admin row + lock row, already locked, no billing obligation."""
    db_session.add(
        Admins(
            username="fuad",
            hashed_password="x",
            marzban_password=ORIGINAL_PASSWORD,
            telegram_id=7531278023,
            panel=marzban_panel.name,
            is_active=True,
            traffic=0,
        )
    )
    db_session.commit()
    bot = FakeBot()
    assert asyncio.run(access_lock.lock_admin(bot, "fuad", "unpaid_invoice"))
    FakeMarzban.reset()
    return bot


def _make_admin(db_session, panel_name, username="fuad", telegram_id=7531278023):
    db_session.add(
        Admins(
            username=username,
            hashed_password="x",
            marzban_password=ORIGINAL_PASSWORD,
            telegram_id=telegram_id,
            panel=panel_name,
            is_active=True,
            traffic=0,
        )
    )
    db_session.commit()


def _backdate_invoice(ledger, invoice_id):
    with ledger._connect() as conn:
        conn.execute(
            "UPDATE invoices SET created_at = ? WHERE id = ?", (LONG_AGO, invoice_id)
        )


def _backdate_debt(ledger, username):
    with ledger._connect() as conn:
        conn.execute(
            "UPDATE debts SET overdue_since = ? WHERE username = ?",
            (LONG_AGO, username),
        )


# --- locking -----------------------------------------------------------------

def test_lock_writes_marzban_then_local_and_keeps_original(
    db_session, marzban_panel, ledger, fake_marzban
):
    _make_admin(db_session, marzban_panel.name)
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    _backdate_invoice(ledger, invoice_id)

    bot = FakeBot()
    asyncio.run(access_lock.tick(bot))

    assert fake_marzban.calls == [("fuad", LOCK_PASSWORD)]
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert admin.marzban_password == LOCK_PASSWORD
    assert verify_password(LOCK_PASSWORD, admin.hashed_password)
    row = ledger.get_admin_lock("fuad")
    assert row is not None
    assert row["original_marzban_password"] == ORIGINAL_PASSWORD
    assert row["reason"] == "unpaid_invoice"
    # Superadmin told, admin told (no password wording).
    notified_ids = {chat_id for chat_id, _ in bot.messages}
    assert 999 in notified_ids
    assert 7531278023 in notified_ids
    for _, text in bot.messages:
        assert LOCK_PASSWORD not in text


def test_grace_period_blocks_premature_lock(
    db_session, marzban_panel, ledger, fake_marzban
):
    _make_admin(db_session, marzban_panel.name)
    ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )

    asyncio.run(access_lock.tick(FakeBot()))

    assert fake_marzban.calls == []
    assert ledger.get_admin_lock("fuad") is None
    assert crud.get_admin_by_username(db_session, "fuad").marzban_password == ORIGINAL_PASSWORD


def test_debt_locks_only_after_overdue_grace(
    db_session, marzban_panel, ledger, fake_marzban
):
    _make_admin(db_session, marzban_panel.name)
    ledger.add_debt("fuad", 7531278023, 500)

    asyncio.run(access_lock.tick(FakeBot()))
    assert ledger.get_admin_lock("fuad") is None

    _backdate_debt(ledger, "fuad")
    asyncio.run(access_lock.tick(FakeBot()))

    assert ledger.get_admin_lock("fuad")["reason"] == "unpaid_debt"
    assert fake_marzban.calls == [("fuad", LOCK_PASSWORD)]


def test_lock_is_idempotent_under_tick_reruns(
    db_session, marzban_panel, ledger, fake_marzban
):
    _make_admin(db_session, marzban_panel.name)
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    _backdate_invoice(ledger, invoice_id)

    asyncio.run(access_lock.tick(FakeBot()))
    asyncio.run(access_lock.tick(FakeBot()))

    assert fake_marzban.calls == [("fuad", LOCK_PASSWORD)]


# --- remote failure ----------------------------------------------------------

def test_remote_failure_changes_nothing(
    db_session, marzban_panel, ledger, fake_marzban
):
    _make_admin(db_session, marzban_panel.name)
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    _backdate_invoice(ledger, invoice_id)
    fake_marzban.status = 500

    asyncio.run(access_lock.tick(FakeBot()))

    admin = crud.get_admin_by_username(db_session, "fuad")
    assert admin.marzban_password == ORIGINAL_PASSWORD
    # The panel-login hash was never touched: "x" is not a bcrypt string.
    assert admin.hashed_password == "x"
    assert ledger.get_admin_lock("fuad") is None


def test_remote_exception_changes_nothing(
    db_session, marzban_panel, ledger, fake_marzban
):
    _make_admin(db_session, marzban_panel.name)
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    _backdate_invoice(ledger, invoice_id)
    fake_marzban.raise_error = True

    asyncio.run(access_lock.tick(FakeBot()))

    admin = crud.get_admin_by_username(db_session, "fuad")
    assert admin.marzban_password == ORIGINAL_PASSWORD
    assert ledger.get_admin_lock("fuad") is None


def test_local_failure_compensates_the_remote_change(
    db_session, marzban_panel, ledger, fake_marzban, monkeypatch
):
    _make_admin(db_session, marzban_panel.name)
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    _backdate_invoice(ledger, invoice_id)

    real_update = crud.update_marzban_password

    def exploding_update(session, admin, new_password):
        raise RuntimeError("local db down")

    monkeypatch.setattr(crud, "update_marzban_password", exploding_update)
    bot = FakeBot()
    asyncio.run(access_lock.lock_admin(bot, "fuad"))
    monkeypatch.setattr(crud, "update_marzban_password", real_update)

    # Remote was asked to lock, then compensated back to the original.
    assert fake_marzban.calls == [
        ("fuad", LOCK_PASSWORD),
        ("fuad", ORIGINAL_PASSWORD),
    ]
    assert ledger.get_admin_lock("fuad") is None
    assert crud.get_admin_by_username(db_session, "fuad").marzban_password == ORIGINAL_PASSWORD


# --- releasing ---------------------------------------------------------------

def test_release_restores_the_exact_original_everywhere(
    locked_admin, db_session, ledger, fake_marzban
):
    bot = locked_admin
    assert asyncio.run(access_lock.release_if_clear(bot, "fuad"))

    assert fake_marzban.calls == [("fuad", ORIGINAL_PASSWORD)]
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert admin.marzban_password == ORIGINAL_PASSWORD
    assert verify_password(ORIGINAL_PASSWORD, admin.hashed_password)
    assert ledger.get_admin_lock("fuad") is None
    notified_ids = {chat_id for chat_id, _ in bot.messages}
    assert 999 in notified_ids
    assert 7531278023 in notified_ids


def test_release_blocked_while_anything_still_owed(
    locked_admin, ledger, fake_marzban
):
    ledger.add_debt("fuad", 7531278023, 500)

    assert asyncio.run(access_lock.release_if_clear(locked_admin, "fuad")) is False
    assert fake_marzban.calls == []
    assert ledger.get_admin_lock("fuad") is not None


def test_tick_releases_when_the_invoice_disappears(
    locked_admin, ledger, fake_marzban
):
    # The fixture locked on no obligation; give and then void an obligation to
    # prove the tick both keeps and drops locks from live billing state.
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    asyncio.run(access_lock.tick(locked_admin))
    assert ledger.get_admin_lock("fuad") is not None

    assert ledger.cancel_invoice(invoice_id)
    asyncio.run(access_lock.tick(locked_admin))

    assert fake_marzban.calls == [("fuad", ORIGINAL_PASSWORD)]
    assert ledger.get_admin_lock("fuad") is None


def test_failed_remote_restore_keeps_the_lock(
    locked_admin, ledger, fake_marzban
):
    fake_marzban.status = 500

    assert asyncio.run(access_lock.release_if_clear(locked_admin, "fuad")) is False
    assert ledger.get_admin_lock("fuad") is not None

    # Panel recovers: the next tick finishes the job.
    fake_marzban.calls.clear()
    fake_marzban.status = 200
    asyncio.run(access_lock.tick(locked_admin))
    assert ledger.get_admin_lock("fuad") is None
    assert fake_marzban.calls == [("fuad", ORIGINAL_PASSWORD)]


# --- observers ---------------------------------------------------------------

def test_observer_is_never_locked_and_an_existing_lock_is_dropped(
    db_session, marzban_panel, ledger, fake_marzban
):
    _make_admin(db_session, marzban_panel.name)
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    _backdate_invoice(ledger, invoice_id)
    ledger.mark_observer_admin("fuad", marked_by=1)

    bot = FakeBot()
    asyncio.run(access_lock.tick(bot))

    assert fake_marzban.calls == []
    assert ledger.get_admin_lock("fuad") is None

    # Lock first, then mark: the mark must release immediately. Marking voids
    # the outstanding invoice, so a fresh one is needed to make them lockable
    # again after un-marking.
    ledger.unmark_observer_admin("fuad")
    invoice_id = ledger.create_invoice(
        telegram_id=7531278023, amount=100, description="d", due_at=None,
        admin_username="fuad",
    )
    _backdate_invoice(ledger, invoice_id)
    asyncio.run(access_lock.tick(bot))
    assert ledger.get_admin_lock("fuad") is not None

    ledger.mark_observer_admin("fuad", marked_by=1)
    asyncio.run(access_lock.force_release_if_locked(bot, "fuad"))
    assert ledger.get_admin_lock("fuad") is None
    assert crud.get_admin_by_username(db_session, "fuad").marzban_password == ORIGINAL_PASSWORD


def test_locked_admin_is_never_offered_to_the_credentials_export(
    locked_admin, db_session, marzban_panel, ledger
):
    # The export path filters on is_locked_admin; assert the primitive it uses.
    assert ledger.is_locked_admin("fuad") is True
    assert access_lock.has_obligation("fuad") is False
