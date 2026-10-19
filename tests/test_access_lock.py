"""Access locks: a reseller who owes money loses the MIT Panel dashboard.

The lock swaps only the local bcrypt hash behind the MIT Panel login and
keeps the exact original hash in the bot database, so payment restores
byte-for-byte what the admin had. Marzban is deliberately never involved —
the reseller's Marzban password, sales bots and user sync stay untouched.
These tests pin the invariants that keep a live panel safe: the lock row is
written before the hash flips, a failed flip leaves no row, release restores
the exact original, observers are never locked, and everything is
idempotent under re-runs.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import pytest

from backend.auth.hash import hash_password, verify_password
from backend.bot import access_lock
from backend.bot.access_lock import LOCK_PASSWORD
from backend.db import crud
from backend.db.model import Admins

# Any timestamp comfortably older than the 12-hour grace period.
LONG_AGO = "2000-01-01T00:00:00+00:00"
ORIGINAL_PASSWORD = "orig-secret"
TELEGRAM_ID = 7531278023


class FakeBot:
    def __init__(self):
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


@pytest.fixture()
def bot_config_stub(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        access_lock, "bot_config", SimpleNamespace(superadmin_id_list=[999])
    )


@pytest.fixture()
def locked_admin(db_session, marzban_panel, ledger, bot_config_stub):
    """An admin row + lock row, already locked, no billing obligation."""
    db_session.add(
        Admins(
            username="fuad",
            hashed_password=hash_password(ORIGINAL_PASSWORD),
            marzban_password="marzban-secret",
            telegram_id=TELEGRAM_ID,
            panel=marzban_panel.name,
            is_active=True,
            traffic=0,
        )
    )
    db_session.commit()
    bot = FakeBot()
    assert asyncio.run(access_lock.lock_admin(bot, "fuad", "unpaid_invoice"))
    return bot


def _make_admin(db_session, panel_name, username="fuad", telegram_id=TELEGRAM_ID):
    db_session.add(
        Admins(
            username=username,
            hashed_password=hash_password(ORIGINAL_PASSWORD),
            marzban_password="marzban-secret",
            telegram_id=telegram_id,
            panel=panel_name,
            is_active=True,
            traffic=0,
        )
    )
    db_session.commit()


def _backdate_debt(ledger, username):
    with ledger._connect() as conn:
        conn.execute(
            "UPDATE debts SET overdue_since = ? WHERE username = ?",
            (LONG_AGO, username),
        )


def _aged_invoice(
    ledger,
    telegram_id=TELEGRAM_ID,
    admin_username="fuad",
    due_at=LONG_AGO,
    created_at=LONG_AGO,
):
    """A pending invoice whose due date (and creation) is already in the past."""
    invoice_id = ledger.create_invoice(
        telegram_id=telegram_id, amount=100, description="d", due_at=due_at,
        admin_username=admin_username,
    )
    if created_at is not None:
        with ledger._connect() as conn:
            conn.execute(
                "UPDATE invoices SET created_at = ? WHERE id = ?",
                (created_at, invoice_id),
            )
    return invoice_id


def _iso(dt: datetime) -> str:
    return dt.isoformat()


# --- locking -----------------------------------------------------------------

def test_lock_swaps_only_the_local_hash_and_keeps_the_original(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(ledger)

    bot = FakeBot()
    asyncio.run(access_lock.tick(bot))

    admin = crud.get_admin_by_username(db_session, "fuad")
    # The mit-panel login now verifies only against the lock password...
    assert verify_password(LOCK_PASSWORD, admin.hashed_password)
    assert not verify_password(ORIGINAL_PASSWORD, admin.hashed_password)
    # ...and Marzban's copy is exactly as it was.
    assert admin.marzban_password == "marzban-secret"

    row = ledger.get_admin_lock("fuad")
    assert row is not None
    assert row["reason"] == "unpaid_invoice"
    assert verify_password(ORIGINAL_PASSWORD, row["original_hashed_password"])

    # Superadmin told, admin told (no password wording).
    notified_ids = {chat_id for chat_id, _ in bot.messages}
    assert 999 in notified_ids
    assert TELEGRAM_ID in notified_ids
    for _, text in bot.messages:
        assert LOCK_PASSWORD not in text


def test_invoice_is_not_locked_before_its_due_date(
    db_session, marzban_panel, ledger, bot_config_stub
):
    # The deploy-day regression: an invoice created long ago but still days
    # away from its deadline must not lock anyone.
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(
        ledger,
        created_at=LONG_AGO,
        due_at=_iso(datetime.now(timezone.utc) + timedelta(days=3)),
    )

    asyncio.run(access_lock.tick(FakeBot()))

    assert ledger.get_admin_lock("fuad") is None
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(ORIGINAL_PASSWORD, admin.hashed_password)


def test_invoice_just_past_due_still_gets_the_grace_period(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(
        ledger,
        due_at=_iso(datetime.now(timezone.utc) - timedelta(hours=1)),
    )

    asyncio.run(access_lock.tick(FakeBot()))

    assert ledger.get_admin_lock("fuad") is None


def test_open_ended_invoice_never_locks(
    db_session, marzban_panel, ledger, bot_config_stub
):
    # due_at None = "no deadline" chosen on purpose — nothing to be past.
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(ledger, due_at=None)

    asyncio.run(access_lock.tick(FakeBot()))

    assert ledger.get_admin_lock("fuad") is None


def test_debt_locks_only_after_overdue_grace(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name)
    ledger.add_debt("fuad", TELEGRAM_ID, 500)

    asyncio.run(access_lock.tick(FakeBot()))
    assert ledger.get_admin_lock("fuad") is None

    _backdate_debt(ledger, "fuad")
    asyncio.run(access_lock.tick(FakeBot()))

    assert ledger.get_admin_lock("fuad")["reason"] == "unpaid_debt"


def test_lock_is_idempotent_under_tick_reruns(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(ledger)

    asyncio.run(access_lock.tick(FakeBot()))
    first_hash = crud.get_admin_by_username(db_session, "fuad").hashed_password
    asyncio.run(access_lock.tick(FakeBot()))
    second_hash = crud.get_admin_by_username(db_session, "fuad").hashed_password

    assert first_hash == second_hash
    assert ledger.get_admin_lock("fuad") is not None


def test_failed_hash_flip_leaves_no_row_and_no_lock(
    db_session, marzban_panel, ledger, bot_config_stub, monkeypatch
):
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(ledger)

    def exploding_hash(password):
        raise RuntimeError("local db down")

    monkeypatch.setattr(access_lock, "hash_password", exploding_hash)
    asyncio.run(access_lock.tick(FakeBot()))
    monkeypatch.setattr(access_lock, "hash_password", hash_password)

    assert ledger.get_admin_lock("fuad") is None
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(ORIGINAL_PASSWORD, admin.hashed_password)
    assert admin.marzban_password == "marzban-secret"


def test_non_bcrypt_original_is_locked_and_restored_verbatim(
    db_session, marzban_panel, ledger, bot_config_stub
):
    # A hash passlib can't parse still round-trips: the row stores the raw
    # string and release writes it back untouched.
    db_session.add(
        Admins(
            username="fuad", hashed_password="not-a-bcrypt-string",
            marzban_password="marzban-secret", telegram_id=TELEGRAM_ID,
            panel=marzban_panel.name, is_active=True, traffic=0,
        )
    )
    db_session.commit()
    _aged_invoice(ledger)

    bot = FakeBot()
    asyncio.run(access_lock.tick(bot))
    assert ledger.get_admin_lock("fuad") is not None
    db_session.expire_all()
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(LOCK_PASSWORD, admin.hashed_password)

    asyncio.run(access_lock.tick(bot))  # still owed — stays locked
    db_session.expire_all()
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(LOCK_PASSWORD, admin.hashed_password)

    with ledger._connect() as conn:
        conn.execute("UPDATE invoices SET status = 'cancelled' WHERE admin_username = ?", ("fuad",))
    asyncio.run(access_lock.tick(bot))
    assert ledger.get_admin_lock("fuad") is None
    db_session.expire_all()
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert admin.hashed_password == "not-a-bcrypt-string"


# --- releasing ---------------------------------------------------------------

def test_release_restores_the_exact_original_hash(
    locked_admin, db_session, ledger, bot_config_stub
):
    bot = locked_admin
    assert asyncio.run(access_lock.release_if_clear(bot, "fuad"))

    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(ORIGINAL_PASSWORD, admin.hashed_password)
    assert not verify_password(LOCK_PASSWORD, admin.hashed_password)
    # Marzban was never part of this and stays untouched.
    assert admin.marzban_password == "marzban-secret"
    assert ledger.get_admin_lock("fuad") is None

    notified_ids = {chat_id for chat_id, _ in bot.messages}
    assert 999 in notified_ids
    assert TELEGRAM_ID in notified_ids


def test_release_blocked_while_anything_still_owed(
    locked_admin, ledger, bot_config_stub
):
    ledger.add_debt("fuad", TELEGRAM_ID, 500)
    _backdate_debt(ledger, "fuad")  # genuinely overdue, not just open

    assert asyncio.run(access_lock.release_if_clear(locked_admin, "fuad")) is False
    assert ledger.get_admin_lock("fuad") is not None


def test_release_happens_when_only_not_yet_due_bills_remain(
    locked_admin, ledger, bot_config_stub
):
    # An open invoice with days to run does not keep anyone locked — the
    # lock criteria and the release criteria are the same predicate.
    _aged_invoice(
        ledger,
        due_at=_iso(datetime.now(timezone.utc) + timedelta(days=3)),
        created_at=None,
    )

    assert asyncio.run(access_lock.release_if_clear(locked_admin, "fuad")) is True
    assert ledger.get_admin_lock("fuad") is None


def test_tick_releases_when_the_invoice_disappears(
    locked_admin, ledger, bot_config_stub
):
    invoice_id = _aged_invoice(ledger)  # past due — keeps the lock alive
    asyncio.run(access_lock.tick(locked_admin))
    assert ledger.get_admin_lock("fuad") is not None

    assert ledger.cancel_invoice(invoice_id)
    asyncio.run(access_lock.tick(locked_admin))

    assert ledger.get_admin_lock("fuad") is None


def test_failed_release_write_keeps_the_row(
    locked_admin, db_session, ledger, bot_config_stub, monkeypatch
):
    from backend.db.engin import sessionLocal as real_factory

    class FailingCommitSession:
        def __init__(self):
            self._inner = real_factory()

        def __enter__(self):
            self._inner.__enter__()
            return self

        def __exit__(self, *exc):
            return self._inner.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def commit(self):
            raise RuntimeError("local db down")

    monkeypatch.setattr(access_lock, "sessionLocal", FailingCommitSession)

    with pytest.raises(RuntimeError):
        asyncio.run(access_lock.release_if_clear(locked_admin, "fuad"))

    monkeypatch.setattr(access_lock, "sessionLocal", real_factory)
    assert ledger.get_admin_lock("fuad") is not None
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(LOCK_PASSWORD, admin.hashed_password)


# --- observers ---------------------------------------------------------------

def test_observer_is_never_locked_and_an_existing_lock_is_dropped(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(ledger)
    ledger.mark_observer_admin("fuad", marked_by=1)

    bot = FakeBot()
    asyncio.run(access_lock.tick(bot))

    assert ledger.get_admin_lock("fuad") is None
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(ORIGINAL_PASSWORD, admin.hashed_password)

    # Lock first, then mark: the mark must release immediately. Marking voids
    # the outstanding invoice, so a fresh one is needed to make them lockable
    # again after un-marking.
    ledger.unmark_observer_admin("fuad")
    _aged_invoice(ledger)
    asyncio.run(access_lock.tick(bot))
    assert ledger.get_admin_lock("fuad") is not None

    ledger.mark_observer_admin("fuad", marked_by=1)
    asyncio.run(access_lock.force_release_if_locked(bot, "fuad"))
    assert ledger.get_admin_lock("fuad") is None
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(ORIGINAL_PASSWORD, admin.hashed_password)


def test_locked_admin_is_flagged_for_the_auth_guard(
    locked_admin, ledger
):
    assert ledger.is_locked_admin("fuad") is True
    assert access_lock.has_obligation("fuad") is False


# --- superadmin manual unlock ------------------------------------------------

def test_manual_unlock_restores_and_suppresses_relocking(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name)
    _aged_invoice(ledger)
    bot = FakeBot()
    asyncio.run(access_lock.tick(bot))
    assert ledger.get_admin_lock("fuad") is not None

    assert asyncio.run(access_lock.manual_unlock(bot, "fuad")) == "unlocked"

    db_session.expire_all()
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(ORIGINAL_PASSWORD, admin.hashed_password)
    assert ledger.get_admin_lock("fuad") is None
    assert ledger.is_lock_exempt("fuad")

    # Still past due, but the monitor must not put the lock back.
    asyncio.run(access_lock.tick(bot))
    assert ledger.get_admin_lock("fuad") is None

    # Settling everything retires the exemption...
    with ledger._connect() as conn:
        conn.execute(
            "UPDATE invoices SET status = 'cancelled' WHERE admin_username = ?",
            ("fuad",),
        )
    asyncio.run(access_lock.tick(bot))
    assert not ledger.is_lock_exempt("fuad")

    # ...so the next genuinely overdue bill locks them again.
    _aged_invoice(ledger)
    asyncio.run(access_lock.tick(bot))
    assert ledger.get_admin_lock("fuad") is not None


def test_manual_unlock_reports_lock_state(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name)
    bot = FakeBot()

    # Nothing locked yet.
    assert asyncio.run(access_lock.manual_unlock(bot, "fuad")) == "no_lock"
    # No such admin at all.
    assert asyncio.run(access_lock.manual_unlock(bot, "nobody")) == "unknown"


def test_unlock_button_lives_in_the_settings_menu():
    from backend.bot import texts, keyboards
    from backend.bot.nav import ALL_MENU_TEXTS

    # Without this the FSM username handler would swallow the tap.
    assert texts.BTN_UNLOCK_ADMIN in ALL_MENU_TEXTS
    rows = [
        [button.text for button in row]
        for row in keyboards.settings_section_kb().keyboard
    ]
    flat = [text for row in rows for text in row]
    assert texts.BTN_UNLOCK_ADMIN in flat
    assert rows[-1] == [texts.BTN_BACK]
