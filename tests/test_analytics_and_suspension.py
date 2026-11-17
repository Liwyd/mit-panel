"""The Analytics page and the suspension reason.

Two features that must never be able to hurt a live panel:

* Analytics only **reads**. Its tables are written by balance changes
  (`_log_sale`, guarded so a missing table skips rather than fails) and by the
  read-only usage recorder — never the other way round, so a chart can't eat a
  charge.
* The suspension reason only **explains** a lock. The hash swap in
  `backend/bot/access_lock.py` is the enforcement; login shows the reason while
  that lock is in place and never on its own, so a stale reason can't keep a
  paying reseller out of their panel.
"""

import asyncio
from datetime import datetime, timedelta

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from backend.auth.hash import hash_password, verify_password
from backend.auth import auth_router
from backend.auth.auth import create_access_token, suspended_message
from backend.bot import access_lock
from backend.bot.access_lock import LOCK_PASSWORD
from backend.db import crud
from backend.db.engin import get_db
from backend.db.model import Admins, AdminTrafficLog, AdminUsageHourly
from backend.schema._input import NodeNamesInput
from backend.utils import analytics, settings_store
from backend.utils.settings_store import get_node_names, set_panel_node_names

ORIGINAL_PASSWORD = "orig-secret"
TELEGRAM_ID = 4242424242


class FakeBot:
    def __init__(self):
        self.messages: list[tuple[int, str]] = []

    async def send_message(self, chat_id, text, **kwargs):
        self.messages.append((chat_id, text))


def _make_admin(db_session, panel_name, username="nima", telegram_id=TELEGRAM_ID):
    db_session.add(
        Admins(
            username=username,
            hashed_password=hash_password(ORIGINAL_PASSWORD),
            panel=panel_name,
            telegram_id=telegram_id,
            is_active=True,
            traffic=100,
            initial_traffic=100,
        )
    )
    db_session.commit()


@pytest.fixture()
def bot_config_stub(monkeypatch):
    from types import SimpleNamespace

    monkeypatch.setattr(
        access_lock, "bot_config", SimpleNamespace(superadmin_id_list=[999])
    )


@pytest.fixture()
def analytics_admin(db_session, marzban_panel):
    """A reseller with a balance, ready to be charged and charted."""
    _make_admin(db_session, marzban_panel.name)
    db_session.expire_all()
    return crud.get_admin_by_username(db_session, "nima")


@pytest.fixture()
def settings_file(tmp_path, monkeypatch):
    """settings_store pointed at a temp file, with its read cache dropped."""
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_PATH", str(path))
    monkeypatch.setattr(settings_store, "DATA_DIR", str(tmp_path))
    _drop_settings_cache()
    yield path
    _drop_settings_cache()


def _drop_settings_cache():
    settings_store._settings_cache = None
    settings_store._settings_cache_time = 0.0


def _admin_app(db_session, role: str, username: str) -> TestClient:
    """The admin router on its own app, with the caller already authenticated."""
    from backend.api.admin import routers as admin_routers
    from backend.auth import get_current_admin

    app = FastAPI()
    app.include_router(admin_routers.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_admin] = lambda: {
        "username": username,
        "role": role,
    }
    return TestClient(app)


def _auth_app(db_session) -> TestClient:
    """The login route plus one route guarded by `get_current_admin`."""
    from backend.auth import get_current_admin

    app = FastAPI()
    app.include_router(auth_router)
    app.dependency_overrides[get_db] = lambda: db_session

    @app.get("/me")
    def me(admin: dict = Depends(get_current_admin)):
        return admin

    return TestClient(app)


def _bot_app(db_session) -> TestClient:
    """The bot router with the shared-secret check disabled."""
    from backend.api.bot import routers as bot_routers
    from backend.auth.auth import verify_bot_api_key

    app = FastAPI()
    app.include_router(bot_routers.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[verify_bot_api_key] = lambda: None
    return TestClient(app)


def _superadmin_app(db_session) -> TestClient:
    from backend.api.superadmin import routers as superadmin_routers
    from backend.auth.auth import get_current_superadmin

    app = FastAPI()
    app.include_router(superadmin_routers.router)
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_current_superadmin] = lambda: {
        "username": "root",
        "role": "superadmin",
    }
    return TestClient(app)


# --- the sales log ----------------------------------------------------------

def test_charge_logs_what_the_balance_actually_gave_up(db_session, analytics_admin):
    """The log records the drop, not the amount asked for.

    `reduce_admin_traffic` clamps at zero; a charge bigger than the balance is
    not a sale of that size, and the daily average would be inflated by it.
    """
    analytics_admin.traffic = 30
    db_session.commit()

    crud.reduce_admin_traffic(db_session, analytics_admin, 1_000)

    row = db_session.query(AdminTrafficLog).one()
    assert row.kind == "charge"
    assert row.amount == 30
    assert crud.get_admin_by_username(db_session, "nima").traffic == 0


def test_refund_is_logged_as_a_negative_sale(db_session, analytics_admin):
    crud.reduce_admin_traffic(db_session, analytics_admin, 40)
    crud.increase_admin_traffic(db_session, analytics_admin, 10)

    amounts = [
        r.amount
        for r in db_session.query(AdminTrafficLog).order_by(AdminTrafficLog.id)
    ]
    assert amounts == [40, -10]
    assert crud.get_admin_by_username(db_session, "nima").traffic == 70


def test_a_missing_log_table_never_undoes_a_charge(db_session, analytics_admin):
    """Reporting is optional; billing is not.

    The analytics tables are created by `init_db`, so a deployment that hasn't
    run it yet must still charge normally — and simply lose the chart row.
    """
    db_session.execute(text("DROP TABLE admin_traffic_log"))
    db_session.commit()

    crud.reduce_admin_traffic(db_session, analytics_admin, 25)

    # The charge landed; only the chart row was lost.
    assert crud.get_admin_by_username(db_session, "nima").traffic == 75
    assert not db_session.execute(
        text("SELECT 1 FROM sqlite_master WHERE type='table' AND name='admin_traffic_log'")
    ).first()


def test_debt_charges_are_sales_too(db_session, analytics_admin):
    """The usage-sync charge drives the balance negative on purpose; the
    analytics daily rate would understate the week without it."""
    crud.reduce_admin_traffic_debt(db_session, analytics_admin, 200)

    admin = crud.get_admin_by_username(db_session, "nima")
    assert admin.traffic == -100
    assert db_session.query(AdminTrafficLog).one().amount == 200


def test_removing_an_admin_takes_its_analytics_with_it(db_session, analytics_admin):
    crud.reduce_admin_traffic(db_session, analytics_admin, 10)
    analytics.record_usage(db_session, analytics_admin.id, 5_000, datetime.utcnow())
    db_session.commit()

    assert crud.remove_admin(db_session, analytics_admin.id)

    assert db_session.query(AdminTrafficLog).count() == 0
    assert db_session.query(AdminUsageHourly).count() == 0


# --- usage buckets ----------------------------------------------------------

def test_usage_lands_in_the_hour_it_was_seen_in(db_session, analytics_admin):
    at = datetime(2026, 5, 10, 8, 41, 12)  # naive UTC
    analytics.record_usage(db_session, analytics_admin.id, 100, at)
    analytics.record_usage(db_session, analytics_admin.id, 50, at)
    db_session.commit()

    row = db_session.query(AdminUsageHourly).one()
    # 08:41 UTC is 11:11 in Tehran (UTC+3:30), so the local hour starts at 08:00.
    assert row.hour == analytics.hour_start(at)
    assert row.used == 150


def test_a_non_positive_reading_records_nothing(db_session, analytics_admin):
    analytics.record_usage(db_session, analytics_admin.id, 0, datetime.utcnow())
    analytics.record_usage(db_session, analytics_admin.id, -5, datetime.utcnow())
    db_session.commit()

    assert db_session.query(AdminUsageHourly).count() == 0


def test_prune_keeps_the_window_and_the_backfill_marker(db_session, analytics_admin):
    old = datetime.utcnow() - timedelta(days=analytics.RETENTION_DAYS + 5)
    fresh = datetime.utcnow() - timedelta(hours=2)
    db_session.add_all(
        [
            AdminUsageHourly(admin_id=analytics_admin.id, hour=old, used=1),
            AdminUsageHourly(admin_id=analytics_admin.id, hour=fresh, used=2),
            AdminTrafficLog(
                admin_id=analytics_admin.id, amount=99, kind="charge", created_at=old
            ),
            # A zero-sized backfill marker must survive: it is what stops the
            # backfill from running a second time.
            AdminTrafficLog(
                admin_id=analytics_admin.id, amount=0, kind="backfill", created_at=old
            ),
        ]
    )
    db_session.commit()

    analytics.prune(db_session)

    assert db_session.query(AdminUsageHourly).one().used == 2
    assert [r.kind for r in db_session.query(AdminTrafficLog).all()] == ["backfill"]


def test_usage_is_bucketed_by_local_day_too(db_session, analytics_admin):
    """23:30 UTC is 03:00 the next day in Tehran, so it belongs to that day."""
    late = datetime(2026, 5, 10, 23, 30)
    analytics.record_usage(db_session, analytics_admin.id, 10, late)
    db_session.commit()

    data = analytics.build_admin_analytics(
        db_session, analytics_admin, now=datetime(2026, 5, 11, 12, 0)
    )
    assert data["usage"]["daily"][-1]["date"] == "2026-05-11"
    assert data["usage"]["daily"][-1]["used"] == 10


# --- the analytics payload --------------------------------------------------

def test_sales_average_and_days_left(db_session, analytics_admin):
    crud.reduce_admin_traffic(db_session, analytics_admin, 40)
    crud.increase_admin_traffic(db_session, analytics_admin, 10)

    data = analytics.build_admin_analytics(db_session, analytics_admin)

    assert data["remaining"] == 70
    assert data["sales"]["window_total"] == 30
    assert data["sales"]["per_day"] == 4  # 30 / 7, whole GB
    assert data["sales"]["days_left"] is not None and data["sales"]["days_left"] > 0
    assert data["usage"]["today"] == 0
    assert len(data["usage"]["hourly"]) == analytics.HOURS_SHOWN
    assert len(data["usage"]["daily"]) == analytics.DAYS_SHOWN


def test_no_sales_lately_means_no_runway_prediction(db_session, analytics_admin):
    data = analytics.build_admin_analytics(db_session, analytics_admin)

    assert data["sales"]["window_total"] == 0
    assert data["sales"]["days_left"] is None
    assert data["sales"]["runs_out_at"] is None


def test_a_spent_balance_says_so(db_session, analytics_admin):
    analytics_admin.traffic = 0
    db_session.commit()

    data = analytics.build_admin_analytics(db_session, analytics_admin)

    assert data["remaining"] == 0
    assert data["sales"]["days_left"] == 0.0


def test_nodes_given_the_same_name_are_shown_as_one():
    nodes = [
        {"id": 1, "name": "Frankfurt", "used": 10},
        {"id": 2, "name": "Frankfurt", "used": 5},
        {"id": None, "name": "Master", "used": 2},
    ]

    merged = analytics.apply_node_names(nodes, {"2": "Frankfurt"})

    assert [n["name"] for n in merged] == ["Frankfurt", "Master"]
    assert merged[0]["used"] == 15


# --- the analytics endpoint -------------------------------------------------

def test_analytics_is_for_admins_only(db_session, analytics_admin):
    client = _admin_app(db_session, role="superadmin", username="test-superadmin")

    assert client.get("/admin/analytics").status_code == 403


def test_analytics_answers_even_when_marzban_cannot_be_read(
    db_session, analytics_admin, monkeypatch
):
    """The node ranking is the only part that talks to Marzban.

    An unreachable panel must degrade to `items: null` and still serve the
    usage and sales charts — never a 500 for the whole page.
    """
    analytics.record_usage(db_session, analytics_admin.id, 700, datetime.utcnow())
    db_session.commit()

    async def unreachable(*args, **kwargs):
        raise OSError("panel is down")

    monkeypatch.setattr(analytics, "admin_node_usage", unreachable)

    body = _admin_app(db_session, role="admin", username="nima").get(
        "/admin/analytics?period=7d"
    ).json()["data"]

    assert body["usage"]["today"] == 700
    assert body["nodes"] == {"period": "7d", "items": None, "total": 0}


def test_analytics_serves_the_node_ranking_and_falls_back_on_a_bad_period(
    db_session, analytics_admin, monkeypatch
):
    async def ranking(*args, **kwargs):
        return [
            {"id": None, "name": "Master", "used": 30},
            {"id": 7, "name": "Frankfurt", "used": 10},
        ]

    monkeypatch.setattr(analytics, "admin_node_usage", ranking)

    body = _admin_app(db_session, role="admin", username="nima").get(
        "/admin/analytics?period=nonsense"
    ).json()["data"]

    assert body["nodes"]["period"] == "1d"  # unknown period falls back
    assert body["nodes"]["total"] == 40
    assert [n["name"] for n in body["nodes"]["items"]] == ["Master", "Frankfurt"]


def test_analytics_404s_for_a_username_with_no_row(db_session):
    client = _admin_app(db_session, role="admin", username="ghost")

    assert client.get("/admin/analytics").status_code == 404


# --- the suspension reason --------------------------------------------------

def test_lock_records_the_reason_and_release_clears_it(
    db_session, marzban_panel, ledger, bot_config_stub
):
    _make_admin(db_session, marzban_panel.name, username="fuad")
    bot = FakeBot()

    assert asyncio.run(access_lock.lock_admin(bot, "fuad", "unpaid_debt"))
    db_session.expire_all()
    assert crud.get_admin_by_username(db_session, "fuad").suspended_reason == "unpaid_debt"

    assert asyncio.run(access_lock.release_admin(bot, "fuad"))
    db_session.expire_all()
    assert crud.get_admin_by_username(db_session, "fuad").suspended_reason is None


def test_a_failed_reason_write_still_leaves_the_lock_in_place(
    db_session, marzban_panel, ledger, bot_config_stub, monkeypatch
):
    """The hash swap is the enforcement; the reason is only the wording.

    If recording the reason fails (a busy database, a column nobody added yet),
    the admin must still be locked out — never let go because a cosmetic write
    failed. `lock_admin` opens three sessions: read, hash swap, reason.
    """
    _make_admin(db_session, marzban_panel.name, username="fuad")

    real = access_lock.sessionLocal
    seen = {"n": 0}

    class CommitFails:
        def __init__(self, session):
            self._session = session

        def __enter__(self):
            self._session.__enter__()
            return self

        def __exit__(self, *exc):
            return self._session.__exit__(*exc)

        def __getattr__(self, name):
            return getattr(self._session, name)

        def commit(self):
            raise RuntimeError("database is busy")

    def factory():
        seen["n"] += 1
        session = real()
        return CommitFails(session) if seen["n"] == 3 else session

    monkeypatch.setattr(access_lock, "sessionLocal", factory)

    bot = FakeBot()
    assert asyncio.run(access_lock.lock_admin(bot, "fuad", "unpaid_invoice")) is True

    db_session.expire_all()
    admin = crud.get_admin_by_username(db_session, "fuad")
    assert verify_password(LOCK_PASSWORD, admin.hashed_password)
    assert ledger.get_admin_lock("fuad") is not None
    assert admin.suspended_reason is None  # the wording was what failed
    assert seen["n"] >= 3  # the reason really was attempted


def test_login_says_why_before_it_checks_the_password(
    db_session, marzban_panel, ledger, bot_config_stub
):
    """A locked admin is typing the password the lock replaced.

    Answering "incorrect password" would leave them guessing; the reason has
    to come first, and it has to be the lock's reason.
    """
    _make_admin(db_session, marzban_panel.name, username="fuad")
    asyncio.run(access_lock.lock_admin(FakeBot(), "fuad", "unpaid_invoice"))

    response = _auth_app(db_session).post(
        "/login", data={"username": "fuad", "password": "the-old-one"}
    )

    assert response.status_code == 403
    message = response.json()["message"]
    assert message == suspended_message("unpaid_invoice")
    assert "incorrect" not in message.lower()


def test_a_stale_reason_alone_never_blocks_a_login(db_session, marzban_panel, ledger):
    """The reason only ever explains a lock that is actually in place.

    If a release failed to clear the column, the reseller must still get in —
    a cosmetic leftover can't hold the dashboard shut.
    """
    _make_admin(db_session, marzban_panel.name, username="fuad")
    crud.set_suspended_reason(
        db_session, crud.get_admin_by_username(db_session, "fuad"), "unpaid_invoice"
    )
    assert ledger.get_admin_lock("fuad") is None

    response = _auth_app(db_session).post(
        "/login", data={"username": "fuad", "password": ORIGINAL_PASSWORD}
    )

    assert response.status_code == 200
    assert response.json()["success"] is True


def test_a_live_session_of_a_locked_admin_is_told_why(
    db_session, marzban_panel, ledger, bot_config_stub
):
    """A lock changes the password, which does nothing to an open session.

    So the guard runs on every request — and now carries the reason, which is
    what sends the frontend back to the login page with an explanation.
    """
    _make_admin(db_session, marzban_panel.name, username="fuad")
    asyncio.run(access_lock.lock_admin(FakeBot(), "fuad", "unpaid_debt"))

    token = create_access_token(
        data={"sub": "fuad", "role": "admin", "panel": marzban_panel.name}
    )
    response = _auth_app(db_session).get(
        "/me", headers={"Authorization": f"Bearer {token}"}
    )

    assert response.status_code == 401
    assert response.json()["detail"] == suspended_message("unpaid_debt")


def test_setting_the_reason_by_hand_does_not_lock_anyone(
    db_session, analytics_admin, ledger
):
    """`POST /bot/admin/suspension` records wording, it does not lock.

    Enforcing on the reason alone would mean an API call could shut a reseller
    out with no lock row and no way back in.
    """
    response = _bot_app(db_session).post(
        "/bot/admin/suspension",
        json={"telegram_id": TELEGRAM_ID, "username": "nima", "reason": "unpaid_invoice"},
    )

    assert response.status_code == 200
    assert response.json()["data"]["reason"] == "unpaid_invoice"
    assert ledger.get_admin_lock("nima") is None
    assert crud.get_admin_by_username(db_session, "nima").suspended_reason == "unpaid_invoice"


def test_suspension_can_be_lifted(db_session, analytics_admin, ledger):
    client = _bot_app(db_session)
    payload = {"telegram_id": TELEGRAM_ID, "username": "nima"}

    client.post("/bot/admin/suspension", json={**payload, "reason": "unpaid_debt"})
    response = client.post("/bot/admin/suspension", json={**payload, "reason": None})

    assert response.status_code == 200
    assert response.json()["data"]["reason"] is None
    assert crud.get_admin_by_username(db_session, "nima").suspended_reason is None


def test_the_bot_cannot_suspend_someone_elses_panel(db_session, analytics_admin):
    """A username this Telegram account doesn't own is not-found, not editable."""
    response = _bot_app(db_session).post(
        "/bot/admin/suspension",
        json={"telegram_id": 999_999, "username": "nima", "reason": "x"},
    )

    assert response.status_code == 404
    assert crud.get_admin_by_username(db_session, "nima").suspended_reason is None


# --- node names -------------------------------------------------------------

def test_node_names_round_trip_and_clear(settings_file):
    saved = set_panel_node_names(3, {"master": "Iran", "7": "  Germany  "})

    assert saved == {"master": "Iran", "7": "Germany"}  # trimmed
    assert get_node_names()["3"] == {"master": "Iran", "7": "Germany"}

    # Another panel's names stay untouched.
    set_panel_node_names(4, {"master": "Turkey"})
    assert set(get_node_names()) == {"3", "4"}

    # Every name blank puts the panel back to Marzban's own names.
    assert set_panel_node_names(3, {"master": " "}) == {}
    assert "3" not in get_node_names()
    assert "4" in get_node_names()


def test_node_names_survive_a_reread_of_the_file(settings_file):
    set_panel_node_names(9, {"master": "Iran"})

    _drop_settings_cache()  # what another process would see
    assert get_node_names()["9"] == {"master": "Iran"}


def test_reading_names_without_the_key_is_an_empty_map(settings_file):
    """A settings.json written before this feature has no `node_names` key."""
    settings_file.write_text('{"login_title": "MIT Panel"}', encoding="utf-8")
    _drop_settings_cache()
    assert get_node_names() == {}


def test_a_corrupt_node_names_value_degrades_to_no_names(settings_file):
    """A hand-edited file must not crash every page that reads settings."""
    settings_file.write_text('{"node_names": 42}', encoding="utf-8")
    _drop_settings_cache()
    assert get_node_names() == {}


def test_the_node_names_endpoint_404s_for_an_unknown_panel(db_session, settings_file):
    response = _superadmin_app(db_session).put(
        "/superadmin/node-names/4242", json={"names": {"master": "Iran"}}
    )

    assert response.status_code == 404
    assert response.json()["message"] == "Marzban panel not found"
    assert get_node_names() == {}


def test_the_node_names_endpoint_saves_and_lists(
    db_session, marzban_panel, settings_file
):
    # Unreachable in tests: the list still comes back with its saved names so
    # they can be edited, which is the whole point of the `reachable` flag.
    marzban_panel.is_active = False
    db_session.commit()
    client = _superadmin_app(db_session)

    saved = client.put(
        f"/superadmin/node-names/{marzban_panel.id}",
        json={"names": {"master": "Iran"}},
    )
    assert saved.status_code == 200
    assert saved.json()["data"] == {"master": "Iran"}

    listed = client.get("/superadmin/node-names").json()["data"]
    assert listed[0]["panel_id"] == marzban_panel.id
    assert listed[0]["reachable"] is False
    assert listed[0]["nodes"][0] == {
        "key": "master",
        "marzban_name": "Master",
        "name": "Iran",
    }


def test_node_names_input_defaults_to_an_empty_map():
    assert NodeNamesInput().names == {}
