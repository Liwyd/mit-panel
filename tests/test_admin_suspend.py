"""Cutting off a late-paying sub-admin's users, and bringing exactly them back.

What has to hold: only users that were active get disabled, each is recorded
before the panel is asked, a read that might be partial changes nothing, and
unsuspending re-enables only what was disabled here — never a user the
sub-admin had switched off themselves.
"""

from __future__ import annotations

import asyncio

import pytest

from backend.bot import suspend
from backend.db.model import Admins, Panels, SanaeiUsers
from backend.services.marzban.api import MarzbanAPIError


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture()
def marzban_admin(db_session, marzban_panel, ledger):
    db_session.add(
        Admins(
            username="ali", hashed_password="x", panel="panel-one",
            marzban_password="pw", telegram_id=555, is_active=True,
        )
    )
    db_session.commit()
    return "ali"


class FakeMarzban:
    """Stands in for backend.services.marzban.APIService."""

    users: list[dict] = []
    statuses: dict[str, str] = {}
    fail_read = False
    fail_set: set[str] = set()
    calls: list[tuple[str, str]] = []

    def __init__(self, url, username, password, inbounds=None):
        self.username = username

    async def get_all_users_paginated(self, page_size=500, page_delay=0.0, *, owners=None):
        if FakeMarzban.fail_read:
            raise MarzbanAPIError("Incomplete user read")
        return [dict(u, status=FakeMarzban.statuses[u["username"]]) for u in FakeMarzban.users]

    async def set_user_status(self, username, status):
        FakeMarzban.calls.append((username, status))
        if username in FakeMarzban.fail_set:
            return 500
        if username not in FakeMarzban.statuses:
            return 404
        FakeMarzban.statuses[username] = status
        return 200


@pytest.fixture()
def fake_marzban(monkeypatch):
    FakeMarzban.users = [
        {"username": "u1", "admin": {"username": "ali"}},
        {"username": "u2", "admin": {"username": "ALI"}},
        {"username": "u3", "admin": {"username": "ali"}},
        {"username": "u4", "admin": {"username": "ali"}},
        {"username": "other", "admin": {"username": "someone"}},
    ]
    FakeMarzban.statuses = {
        "u1": "active", "u2": "active", "u3": "disabled", "u4": "expired", "other": "active",
    }
    FakeMarzban.fail_read = False
    FakeMarzban.fail_set = set()
    FakeMarzban.calls = []
    monkeypatch.setattr(suspend, "MarzbanAPI", FakeMarzban)
    return FakeMarzban


def test_init_db_can_run_twice(ledger):
    ledger.init_db()
    ledger.init_db()
    assert ledger.list_suspensions() == []


def test_only_the_admins_active_users_are_disabled_and_recorded(marzban_admin, fake_marzban, ledger):
    result = _run(suspend.suspend_admin("ali", by=1))
    assert (result.done, result.failed, result.total) == (2, 0, 2)
    assert fake_marzban.statuses == {
        "u1": "disabled", "u2": "disabled", "u3": "disabled", "u4": "expired", "other": "active",
    }
    assert [r["user_key"] for r in ledger.pending_suspended_users("ali")] == ["u1", "u2"]
    row = ledger.get_suspension("ali")
    assert row["panel_type"] == "marzban" and row["telegram_id"] == 555 and row["suspended_by"] == 1


def test_a_partial_read_changes_nothing(marzban_admin, fake_marzban, ledger):
    fake_marzban.fail_read = True
    with pytest.raises(suspend.SuspendError):
        _run(suspend.suspend_admin("ali"))
    assert fake_marzban.calls == []
    assert ledger.get_suspension("ali") is None


def test_a_user_that_failed_to_disable_is_not_kept(marzban_admin, fake_marzban, ledger):
    fake_marzban.fail_set = {"u2"}
    result = _run(suspend.suspend_admin("ali"))
    assert (result.done, result.failed) == (1, 1)
    assert [r["user_key"] for r in ledger.pending_suspended_users("ali")] == ["u1"]


def test_unsuspend_brings_back_only_what_was_disabled_here(marzban_admin, fake_marzban, ledger):
    _run(suspend.suspend_admin("ali"))
    del fake_marzban.statuses["u2"]  # deleted while suspended
    result = _run(suspend.unsuspend_admin("ali"))
    assert (result.done, result.skipped, result.failed) == (1, 1, 0)
    assert fake_marzban.statuses["u1"] == "active"
    assert fake_marzban.statuses["u3"] == "disabled"  # the sub-admin's own choice
    assert ledger.get_suspension("ali") is None


def test_a_failed_restore_stays_recorded_for_the_next_try(marzban_admin, fake_marzban, ledger):
    _run(suspend.suspend_admin("ali"))
    fake_marzban.fail_set = {"u2"}
    result = _run(suspend.unsuspend_admin("ali"))
    assert (result.done, result.failed) == (1, 1)
    assert [r["user_key"] for r in ledger.pending_suspended_users("ali")] == ["u2"]
    assert ledger.get_suspension("ali") is not None
    fake_marzban.fail_set = set()
    _run(suspend.unsuspend_admin("ali"))
    assert fake_marzban.statuses["u2"] == "active"
    assert ledger.get_suspension("ali") is None


def test_suspending_again_only_adds_newly_active_users(marzban_admin, fake_marzban, ledger):
    _run(suspend.suspend_admin("ali"))
    first = ledger.get_suspension("ali")["suspended_at"]
    fake_marzban.statuses["u4"] = "active"  # re-enabled by the sub-admin
    result = _run(suspend.suspend_admin("ali"))
    assert result.done == 1
    assert ledger.get_suspension("ali")["suspended_at"] == first
    assert [r["user_key"] for r in ledger.pending_suspended_users("ali")] == ["u1", "u2", "u4"]


def test_nothing_to_suspend_records_nothing(marzban_admin, fake_marzban, ledger):
    for k in fake_marzban.statuses:
        fake_marzban.statuses[k] = "disabled"
    result = _run(suspend.suspend_admin("ali"))
    assert result.total == 0
    assert ledger.get_suspension("ali") is None


def test_unsupported_panels_are_refused(db_session, ledger):
    db_session.add(Panels(panel_type="guard", name="g", url="http://g", username="a", password="b"))
    db_session.add(Admins(username="gg", hashed_password="x", panel="g", is_active=True))
    db_session.commit()
    with pytest.raises(suspend.SuspendError):
        _run(suspend.suspend_admin("gg"))
    assert [a.username for a in suspend.suspendable_admins()] == []


# ------------------------------------------------------------------ 3x-ui


class FakeSanaei:
    clients: list[dict] = []
    fail_read = False
    updates: list[dict] = []

    def __init__(self, url, token):
        pass

    async def get_clients(self):
        if FakeSanaei.fail_read:
            raise RuntimeError("panel down")
        return [dict(c) for c in FakeSanaei.clients]

    async def set_client_enable(self, client, enable):
        FakeSanaei.updates.append({"email": client["email"], "enable": enable, "totalGB": client.get("totalGB")})
        for c in FakeSanaei.clients:
            if c["email"] == client["email"]:
                c["enable"] = enable
        return True

    async def close(self):
        pass


@pytest.fixture()
def sanaei_admin(db_session, ledger, monkeypatch):
    db_session.add(Panels(panel_type="3x-ui", name="x", url="http://x", username="a", password="b", token="t"))
    db_session.add(Admins(username="sara", hashed_password="x", panel="x", is_active=True))
    db_session.add_all([SanaeiUsers(username=n, owner="sara") for n in ("c1", "c2", "c3")])
    db_session.add(SanaeiUsers(username="c9", owner="someone"))
    db_session.commit()
    FakeSanaei.clients = [
        {"id": "id1", "email": "c1", "enable": True, "totalGB": 0, "expiryTime": 0},
        {"id": "id2", "email": "c2", "enable": False, "totalGB": 10, "expiryTime": 0},
        {"id": "id3", "email": "c3", "enable": True, "totalGB": 5, "expiryTime": 9},
        {"id": "id9", "email": "c9", "enable": True, "totalGB": 5, "expiryTime": 9},
    ]
    FakeSanaei.fail_read = False
    FakeSanaei.updates = []
    monkeypatch.setattr(suspend, "SanaeiAPI", FakeSanaei)
    return "sara"


def test_3xui_disables_only_owned_enabled_clients_and_restores_them(sanaei_admin, ledger):
    result = _run(suspend.suspend_admin("sara"))
    assert result.done == 2
    assert {c["email"]: c["enable"] for c in FakeSanaei.clients} == {
        "c1": False, "c2": False, "c3": False, "c9": True,
    }
    _run(suspend.unsuspend_admin("sara"))
    assert {c["email"]: c["enable"] for c in FakeSanaei.clients} == {
        "c1": True, "c2": False, "c3": True, "c9": True,
    }
    assert ledger.get_suspension("sara") is None


def test_3xui_read_error_is_not_an_empty_reseller(sanaei_admin, ledger):
    FakeSanaei.fail_read = True
    with pytest.raises(suspend.SuspendError):
        _run(suspend.suspend_admin("sara"))
    assert FakeSanaei.updates == []


def test_new_menu_labels_never_reach_a_waiting_flow():
    from backend.bot import texts
    from backend.bot.nav import ALL_MENU_TEXTS
    from backend.bot.routers import all_routers

    for label in (texts.BTN_SUSPEND_ADMIN, texts.BTN_UNSUSPEND_ADMIN, texts.BTN_DELETE_BOT):
        assert label in ALL_MENU_TEXTS
    assert "suspend" in {r.name for r in all_routers}
