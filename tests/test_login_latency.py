"""A login must answer in milliseconds, never on Marzban's schedule.

The login route used to refresh an all-inbounds admin's inbound list inline:
the Marzban read retries 3x at its full timeout, so whenever the upstream
panel was slow (production, 2026-11-16) every login of such an admin sat
~30s — past the seller bots' 8s deadline. A paying customer's delivery died
with "context deadline exceeded" and the failed logins themselves re-triggered
the refresh, amplifying the storm. The refresh now runs after the response.
"""

import asyncio
import json
import time

from fastapi import FastAPI
from fastapi.testclient import TestClient

import backend.services.marzban as marzban_pkg
from backend.auth import auth
from backend.auth import hash as auth_hash
from backend.auth.auth import router as auth_router
from backend.db import crud
from backend.db.engin import get_db
from backend.db.model import Admins
from backend.services.marzban.api import MarzbanAPIError

INBOUNDS = {"vmess": ["vmess-tag"], "vless": ["vless-tag", "vless-tag-2"]}
ADMIN = "selleradmin"
PASSWORD = "pw"


def build_client(db_session):
    """The auth router on its own app, with the test database behind it."""
    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = lambda: db_session
    return TestClient(app)


def make_admin(db_session, all_inbounds: bool = True):
    db_session.add(
        Admins(
            username=ADMIN,
            hashed_password=auth_hash.hash_password(PASSWORD),
            panel="panel-one",
            marzban_all_inbounds=all_inbounds,
        )
    )
    db_session.commit()


def login(client):
    return client.post("/login", data={"username": ADMIN, "password": PASSWORD})


def stored_inbounds(db_session):
    db_session.expire_all()
    admin = crud.get_admin_by_username(db_session, ADMIN)
    return json.loads(admin.marzban_inbounds) if admin.marzban_inbounds else None


def test_a_slow_marzban_read_cannot_delay_the_login(monkeypatch, db_session, marzban_panel):
    make_admin(db_session)

    class SlowAPI:
        def __init__(self, url=None, username=None, password=None):
            pass

        async def get_inbounds(self):
            await asyncio.sleep(10.0)  # the full stuck-Marzban read, retried thrice in prod
            return dict(INBOUNDS)

    monkeypatch.setattr(marzban_pkg, "APIService", SlowAPI)

    client = build_client(db_session)
    started = time.monotonic()
    response = login(client)
    elapsed = time.monotonic() - started

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]
    assert elapsed < 2.5, f"login took {elapsed:.2f}s — it still waits on Marzban"


def test_the_background_refresh_updates_the_stored_inbounds(
    monkeypatch, db_session, marzban_panel
):
    make_admin(db_session)

    class FastAPIFake:
        def __init__(self, url=None, username=None, password=None):
            pass

        async def get_inbounds(self):
            return dict(INBOUNDS)

    monkeypatch.setattr(marzban_pkg, "APIService", FastAPIFake)

    asyncio.run(auth._refresh_all_inbounds(ADMIN))

    assert stored_inbounds(db_session) == INBOUNDS


def test_a_failing_marzban_read_never_breaks_the_login_or_raises(
    monkeypatch, db_session, marzban_panel
):
    make_admin(db_session)

    class BrokenAPI:
        def __init__(self, url=None, username=None, password=None):
            pass

        async def get_inbounds(self):
            raise MarzbanAPIError("upstream slow")

    monkeypatch.setattr(marzban_pkg, "APIService", BrokenAPI)

    client = build_client(db_session)
    response = login(client)
    asyncio.run(auth._refresh_all_inbounds(ADMIN))  # must swallow, not raise

    assert response.status_code == 200
    assert response.json()["data"]["access_token"]
    assert stored_inbounds(db_session) is None


def test_a_plain_admin_login_skips_the_refresh_entirely(
    monkeypatch, db_session, marzban_panel
):
    make_admin(db_session, all_inbounds=False)

    constructed = []

    class WatchingAPI:
        def __init__(self, url=None, username=None, password=None):
            constructed.append(1)

        async def get_inbounds(self):
            return dict(INBOUNDS)

    monkeypatch.setattr(marzban_pkg, "APIService", WatchingAPI)

    asyncio.run(auth._refresh_all_inbounds(ADMIN))

    assert constructed == [], "a plain admin must not touch Marzban at login"
    assert stored_inbounds(db_session) is None
