"""Provisioning must never create a panel without an inbound set.

Three code paths create reseller panels (the shop purchase, the superadmin
menu form, and the bot's HTTP endpoint).  All three used to swallow inbound
read failures and store `marzban_inbounds = None`, which left the panel
unable to hand out configs that connect to anything.  Each path is covered
here so a fix to one cannot silently regress the others.
"""

import asyncio
import json

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.api.bot import routers
from backend.db.engin import get_db
from backend.db.model import Admins
from backend.services.marzban import api as marzban_api

INBOUNDS = {"vmess": ["vmess-tag"], "vless": ["vless-tag", "vless-tag-2"]}


class FakeMarzbanAPI:
    """Stands in for the Marzban API and records what provisioning asked of it."""

    def __init__(self, url, username, password, inbounds=None, *, live=None,
                 inbound_error=None, create_status=200):
        self.url = url
        self.username = username
        self.password = password
        self.inbounds = inbounds or {}
        self.live = live
        self.inbound_error = inbound_error
        self.create_status = create_status
        self.calls = {"inbounds": 0, "create_admin": []}

    async def get_inbounds(self):
        self.calls["inbounds"] += 1
        if self.inbound_error is not None:
            raise self.inbound_error
        return self.live

    async def create_admin(self, username, password, telegram_id=None):
        self.calls["create_admin"].append((username, password, telegram_id))
        return self.create_status, "duplicate"


def install_fake_api(monkeypatch, **kwargs):
    """Replace APIService with the fake and return the instance it built."""
    holder = {}

    class Factory(FakeMarzbanAPI):
        def __init__(self, url, username, password, inbounds=None):
            super().__init__(url, username, password, inbounds, **kwargs)
            holder["instance"] = self

    monkeypatch.setattr(marzban_api, "APIService", Factory)
    # `panel_client` imports APIService inside the function (resolved at call
    # time), but the bot router imported it at module load — patch that binding
    # too, or the endpoint tests would still reach the real client.
    if hasattr(routers, "MarzbanAPI"):
        monkeypatch.setattr(routers, "MarzbanAPI", Factory)
    return holder


def get_admin(db_session, username):
    db_session.expire_all()
    return db_session.query(Admins).filter_by(username=username).first()


def test_shop_purchase_stores_every_inbound_and_flags_all_inbounds(
    monkeypatch, db_session, marzban_panel, panel_client, admin_row
):
    fake = install_fake_api(monkeypatch, live=dict(INBOUNDS))

    result = asyncio.run(
        panel_client.create_admin_for_shop(
            username="shopadmin", password="pw", panel="panel-one",
            traffic_gb=200.0, telegram_id=111,
        )
    )

    assert result["username"] == "shopadmin"

    admin = admin_row("shopadmin")
    assert admin is not None, "the panel row must be written"
    assert admin.marzban_all_inbounds is True
    assert json.loads(admin.marzban_inbounds) == INBOUNDS
    assert admin.traffic == 200 * 1024**3
    assert admin.initial_traffic == 200 * 1024**3

    instance = fake["instance"]
    assert instance.calls["create_admin"] == [("shopadmin", "pw", 111)]
    assert instance.calls["inbounds"] == 1


def test_superadmin_form_stores_every_inbound_and_flags_all_inbounds(
    monkeypatch, db_session, marzban_panel, panel_client, admin_row
):
    fake = install_fake_api(monkeypatch, live=dict(INBOUNDS))

    result = asyncio.run(
        panel_client.create_admin(
            username="formadmin", password="pw", panel="panel-one",
            traffic_gb=50.0, expiry_days=30, telegram_id=None,
        )
    )

    assert result["inbounds"] == INBOUNDS

    admin = admin_row("formadmin")
    assert admin.marzban_all_inbounds is True
    assert json.loads(admin.marzban_inbounds) == INBOUNDS
    assert admin.expiry_date is not None
    assert fake["instance"].calls["create_admin"] == [("formadmin", "pw", None)]


def test_unreadable_inbounds_abort_before_marzban_is_touched(
    monkeypatch, db_session, marzban_panel, panel_client, admin_row
):
    """A failed read must not leave a reseller half-created in Marzban."""
    fake = install_fake_api(
        monkeypatch, live=None, inbound_error=marzban_api.MarzbanAPIError("boom")
    )

    with pytest.raises(panel_client.PanelClientError, match="inbounds"):
        asyncio.run(
            panel_client.create_admin_for_shop(
                username="nevermade", password="pw", panel="panel-one",
                traffic_gb=10.0, telegram_id=111,
            )
        )

    assert fake["instance"].calls["create_admin"] == []
    assert admin_row("nevermade") is None


def test_empty_inbounds_are_refused(
    monkeypatch, db_session, marzban_panel, panel_client, admin_row
):
    fake = install_fake_api(monkeypatch, live={})

    with pytest.raises(panel_client.PanelClientError, match="no inbounds"):
        asyncio.run(
            panel_client.create_admin(
                username="nevermade", password="pw", panel="panel-one",
                traffic_gb=10.0, expiry_days=None, telegram_id=None,
            )
        )

    assert fake["instance"].calls["create_admin"] == []
    assert admin_row("nevermade") is None


def test_bot_endpoint_provisions_with_all_inbounds(
    monkeypatch, db_session, marzban_panel, admin_row
):
    client = build_bot_client(db_session)
    install_fake_api(monkeypatch, live=dict(INBOUNDS))

    response = client.post(
        "/bot/admin/create",
        headers={"X-Bot-Api-Key": "test-bot-key"},
        json={
            "username": "apiadmin",
            "password": "pw",
            "panel": "panel-one",
            "traffic_gb": 15.0,
            "telegram_id": None,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["data"]["inbounds"] == INBOUNDS

    admin = admin_row("apiadmin")
    assert admin.marzban_all_inbounds is True
    assert json.loads(admin.marzban_inbounds) == INBOUNDS


def test_bot_endpoint_fails_loudly_when_inbounds_cannot_be_read(
    monkeypatch, db_session, marzban_panel, admin_row
):
    client = build_bot_client(db_session)
    install_fake_api(
        monkeypatch, live=None, inbound_error=marzban_api.MarzbanAPIError("boom")
    )

    response = client.post(
        "/bot/admin/create",
        headers={"X-Bot-Api-Key": "test-bot-key"},
        json={
            "username": "apiadmin",
            "password": "pw",
            "panel": "panel-one",
            "traffic_gb": 15.0,
        },
    )

    assert response.status_code == 502
    assert "inbounds" in response.json()["message"].lower()
    assert admin_row("apiadmin") is None


def build_bot_client(db_session):
    """The bot router on its own app, with the test database behind it."""
    app = FastAPI()
    app.include_router(routers.router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)
