"""A Marzban user the bot really created must always be ledgered, even when the
panel's HTTP response is lost.

Regression for a production incident: a reseller created a user through the bot,
the Marzban panel created it, but the create call timed out (the panel is often
slow). `add_user_to_panel` returned False, so no `marzban_users` row was written,
and the twice-daily usage sync then billed the reseller for their own sale as
"created outside the bot" (خارج از ربات), driving their balance negative and
issuing an invoice.

The fix (backend/services/task_handler.py): on a create that reports failure,
confirm against Marzban; if the user really exists and belongs to this admin, it
was created and is ledgered (and charged once). The retry path also adopts an
admin's own user that already exists on the panel but was never ledgered.
"""

import asyncio

import pytest
from requests import Timeout

from backend.db import crud
from backend.db.model import Admins
from backend.schema._input import ClientInput
from backend.services import task_handler
from backend.services.marzban.api import APIService

GB = 1024**3
USER = "manikavousian"


@pytest.fixture()
def reseller(db_session, marzban_panel):
    """A non-tracked (traffic-balance) Marzban reseller with quota to spare."""
    db_session.add(
        Admins(
            username="matinsh",
            hashed_password="x",
            is_active=True,
            panel=marzban_panel.name,
            marzban_password="mp",
            marzban_all_inbounds=False,
            traffic=500 * GB,
            initial_traffic=500 * GB,
        )
    )
    db_session.commit()
    return crud.get_admin_by_username(db_session, "matinsh")


def _client(total=100 * GB):
    return ClientInput(email=USER, id="uuid", sub_id="sub", total=total, expiry_time=0)


def _owned(username=USER, owner="matinsh", limit=100 * GB):
    return {"username": username, "data_limit": limit, "admin": {"username": owner}}


def _patch_api(monkeypatch, *, on_create, pre_exists=None, confirm=None):
    """Wire the three APIService methods add_new_user touches.

    pre_exists: what the duplicate pre-check read returns (None => a not-found
    body). on_create: the coroutine run in place of create_user. confirm: what
    the post-failure confirming read (get_billing_user) returns.
    """

    async def get_user(_self, username):
        return pre_exists if pre_exists is not None else {"detail": "Not Found"}

    async def get_billing_user(_self, username):
        return confirm

    monkeypatch.setattr(APIService, "get_user", get_user)
    monkeypatch.setattr(APIService, "get_billing_user", get_billing_user)
    monkeypatch.setattr(APIService, "create_user", on_create)


def test_timed_out_create_that_landed_is_recorded_and_charged_once(
    db_session, reseller, monkeypatch
):
    created = []

    async def create(_self, payload):
        created.append(payload.email)
        raise Timeout("the response was lost")  # ...but Marzban made the user

    _patch_api(monkeypatch, on_create=create, confirm=_owned())

    result = asyncio.run(task_handler.add_new_user("matinsh", _client(), db_session))

    assert getattr(result, "success", False) is True
    row = crud.get_marzban_user(db_session, "matinsh", USER)
    assert row is not None and row.source == "bot"
    db_session.refresh(reseller)
    assert reseller.traffic == 400 * GB  # charged exactly once
    assert created == [USER]  # attempted once, never replayed


def test_genuine_failure_records_nothing_and_does_not_charge(
    db_session, reseller, monkeypatch
):
    async def create(_self, payload):
        raise Timeout("panel unreachable")  # and the user was NOT created

    _patch_api(monkeypatch, on_create=create, confirm=None)  # confirm: absent

    result = asyncio.run(task_handler.add_new_user("matinsh", _client(), db_session))

    assert result.status_code == 400
    assert crud.get_marzban_user(db_session, "matinsh", USER) is None
    db_session.refresh(reseller)
    assert reseller.traffic == 500 * GB  # untouched


def test_retry_adopts_the_admins_own_unledgered_user(db_session, reseller, monkeypatch):
    created = []

    async def create(_self, payload):
        created.append(payload.email)
        return 200

    _patch_api(monkeypatch, on_create=create, pre_exists=_owned())

    result = asyncio.run(task_handler.add_new_user("matinsh", _client(), db_session))

    assert getattr(result, "success", False) is True
    row = crud.get_marzban_user(db_session, "matinsh", USER)
    assert row is not None and row.source == "bot"
    db_session.refresh(reseller)
    assert reseller.traffic == 400 * GB
    assert created == []  # the pre-check adopted it; create never ran


def test_retry_does_not_adopt_a_user_owned_by_someone_else(
    db_session, reseller, monkeypatch
):
    async def create(_self, payload):
        raise AssertionError("must not create when the name belongs to another admin")

    _patch_api(monkeypatch, on_create=create, pre_exists=_owned(owner="someone_else"))

    result = asyncio.run(task_handler.add_new_user("matinsh", _client(), db_session))

    assert result.status_code == 409
    assert crud.get_marzban_user(db_session, "matinsh", USER) is None
    db_session.refresh(reseller)
    assert reseller.traffic == 500 * GB
