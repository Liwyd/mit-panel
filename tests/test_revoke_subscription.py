import asyncio
import json

import pytest

from backend.api.admin import routers
from backend.db.model import Admins, MarzbanUsers
from backend.services.marzban.api import MarzbanUserUnavailable


@pytest.fixture
def reseller(db_session, marzban_panel):
    admin = Admins(username="reseller", hashed_password="hash", panel=marzban_panel.name,
                   marzban_password="reseller-secret", is_active=True, traffic=1234)
    db_session.add_all([admin, MarzbanUsers(owner="reseller", username="alice", data_limit=456)])
    db_session.commit()
    return admin


def call(db, role="admin", username="alice"):
    return asyncio.run(routers.revoke_subscription(username, db, {"role": role, "username": "reseller"}))


def test_revoke_uses_reseller_credentials_and_preserves_accounting(db_session, reseller, monkeypatch):
    calls = []
    class FakeAPI:
        def __init__(self, url, username, password):
            calls.append((url, username, password))

        async def revoke_subscription(self, username):
            calls.append(username)
            return {"username": username, "subscription_url": "/sub/new"}

    monkeypatch.setattr(routers, "APIService", FakeAPI)
    result = call(db_session)
    assert result["data"]["subscription_url"] == "/sub/new"
    assert calls == [("http://marzban.test:8000", "reseller", "reseller-secret"), "alice"]
    db_session.refresh(reseller)
    assert reseller.traffic == 1234
    row = db_session.query(MarzbanUsers).one()
    assert (row.owner, row.username, row.data_limit) == ("reseller", "alice", 456)


@pytest.mark.parametrize("condition", ["inactive", "other_panel", "wrong_role"])
def test_revoke_rejects_unpermitted_requests(db_session, reseller, marzban_panel, monkeypatch, condition):
    if condition == "inactive":
        reseller.is_active = False
    if condition == "other_panel":
        marzban_panel.panel_type = "guard"
    db_session.commit()
    monkeypatch.setattr(routers, "APIService", lambda *args: pytest.fail("upstream must not be called"))
    response = call(db_session, role="superadmin" if condition == "wrong_role" else "admin")
    assert response.status_code == (400 if condition == "other_panel" else 403)


def test_revoke_hides_unavailable_user(db_session, reseller, monkeypatch):
    class FakeAPI:
        def __init__(self, *args):
            pass

        async def revoke_subscription(self, username):
            raise MarzbanUserUnavailable()

    monkeypatch.setattr(routers, "APIService", FakeAPI)
    response = call(db_session)
    assert response.status_code == 404
    assert json.loads(response.body)["message"] == "User unavailable"
