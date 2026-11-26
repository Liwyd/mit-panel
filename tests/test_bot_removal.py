"""Deleting a sales bot for good.

The panel can only ask the mit-seller server to delete a bot, so what matters
here is the order: the bot is forgotten by the panel only after the server
said it is gone, and a refusal leaves the row in place so the superadmin can
still see the bot and try again.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.db import crud
from backend.db.engin import get_db
from backend.utils import bot_removal, mitseller

from tests.test_mitseller_integration import _transport, settings_stub  # noqa: F401


def _bot(db_session, url="https://bot7.example.com") -> int:
    """A connected bot's id (an id, so a test can still use it once the row is gone)."""
    return crud.add_bot(
        db_session, name="@shopbot", url=url, owner_key="o" * 32,
        manager_key="m" * 32, bot_username="shopbot", is_active=True,
    ).id


def _app(db_session, role: str) -> TestClient:
    from backend.api.bots import routers as bots_routers
    from backend.auth import get_current_admin

    app = FastAPI()
    app.include_router(bots_routers.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_admin] = lambda: {"username": "x", "role": role}
    return TestClient(app)


@pytest.mark.parametrize(
    "url,domain",
    [
        ("https://Bot7.Example.com", "bot7.example.com"),
        ("https://bot7.example.com/", "bot7.example.com"),
        ("bot7.example.com", "bot7.example.com"),
        ("https://bot7.example.com:8443/x", "bot7.example.com"),
    ],
)
def test_the_domain_comes_from_the_stored_address(url, domain):
    assert bot_removal.bot_domain(url) == domain


def test_deprovision_sends_the_domain_and_the_backup_choice(settings_stub, monkeypatch):
    seen = {}

    def handler(request: httpx.Request):
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("authorization")
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"ok": True, "data": {"n": 7, "domain": "bot7.example.com"}})

    monkeypatch.setattr(mitseller.httpx, "AsyncClient", _transport(handler))
    data = asyncio.run(mitseller.deprovision_bot(domain="Bot7.example.com", final_backup=False))
    assert data["n"] == 7
    assert seen["url"] == "https://176.124.199.78:18100/deprovision"
    assert seen["auth"] == "Bearer " + "a" * 64
    assert seen["body"] == {"domain": "bot7.example.com", "final_backup": False}


@pytest.mark.parametrize(
    "status,body,match",
    [
        (404, {"ok": False, "error": "no bot"}, "نصب نیست"),
        (405, None, "به‌روز"),
        (502, {"ok": False, "error": "could not send the final backup"}, "final backup"),
    ],
)
def test_deprovision_reports_every_refusal(settings_stub, monkeypatch, status, body, match):
    def handler(request):
        if body is None:
            return httpx.Response(status, text="Method Not Allowed")
        return httpx.Response(status, json=body)

    monkeypatch.setattr(mitseller.httpx, "AsyncClient", _transport(handler))
    with pytest.raises(mitseller.MitSellerError, match=match):
        asyncio.run(mitseller.deprovision_bot(domain="bot7.example.com"))


def test_the_row_goes_only_after_the_server_removed_the_bot(db_session, settings_stub, monkeypatch):
    bot_id = _bot(db_session)
    calls = []

    async def ok(*, domain, final_backup):
        calls.append((domain, final_backup))
        return {"n": 7}

    monkeypatch.setattr(mitseller, "deprovision_bot", ok)
    removed = asyncio.run(bot_removal.remove_bot_completely(bot_id, final_backup=True))
    assert removed == {"name": "@shopbot", "domain": "bot7.example.com"}
    assert calls == [("bot7.example.com", True)]
    db_session.expire_all()
    assert crud.get_bot_by_id(db_session, bot_id) is None


def test_a_refused_removal_keeps_the_row(db_session, settings_stub, monkeypatch):
    bot_id = _bot(db_session)

    async def refuse(**_):
        raise mitseller.MitSellerError("could not send the final backup")

    monkeypatch.setattr(mitseller, "deprovision_bot", refuse)
    with pytest.raises(bot_removal.BotRemovalError, match="final backup"):
        asyncio.run(bot_removal.remove_bot_completely(bot_id))
    db_session.expire_all()
    assert crud.get_bot_by_id(db_session, bot_id) is not None


def test_only_the_superadmin_may_destroy_a_bot(db_session, settings_stub, monkeypatch):
    bot_id = _bot(db_session)

    async def never(**_):
        raise AssertionError("an admin reached the server")

    monkeypatch.setattr(mitseller, "deprovision_bot", never)
    res = _app(db_session, "admin").post(f"/sales-bots/manage/{bot_id}/destroy", json={})
    assert res.status_code == 403


def test_the_superadmin_destroys_a_bot_through_the_api(db_session, settings_stub, monkeypatch):
    bot_id = _bot(db_session)
    seen = {}

    async def ok(*, domain, final_backup):
        seen["final_backup"] = final_backup
        return {}

    monkeypatch.setattr(mitseller, "deprovision_bot", ok)
    res = _app(db_session, "superadmin").post(
        f"/sales-bots/manage/{bot_id}/destroy", json={"final_backup": False}
    )
    assert res.status_code == 200 and res.json()["success"] is True
    assert seen["final_backup"] is False
    db_session.expire_all()
    assert crud.get_bot_by_id(db_session, bot_id) is None
