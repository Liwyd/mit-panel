"""Hosting billing against a shared file DB, like production (never live data)."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.bot import access_lock, approvals, maintenance as hosting, texts
from backend.db import crud
from backend.db.engin import Base
from backend.db.model import Admins, TelegramBots

NOW = datetime(2026, 1, 31, 9, 15, tzinfo=timezone.utc)


@pytest.fixture
def shared_db(ledger, monkeypatch, tmp_path):
    engine = create_engine(f"sqlite:///{ledger.bot_config.sqlite_path}")
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    import backend.db.engin as engin

    monkeypatch.setattr(engin, "sessionLocal", factory)
    monkeypatch.setattr(access_lock, "sessionLocal", factory)
    monkeypatch.setattr(approvals, "sessionLocal", factory)
    monkeypatch.setattr(
        hosting, "bot_config", SimpleNamespace(superadmin_id_list=[999])
    )
    from backend.utils import settings_store

    monkeypatch.setattr(
        settings_store, "SETTINGS_PATH", str(tmp_path / "settings.json")
    )
    monkeypatch.setattr(settings_store, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(settings_store, "_settings_cache", None)
    monkeypatch.setattr(settings_store, "_settings_cache_time", 0)
    with factory() as session:
        session.add(
            Admins(
                id=1,
                username="buyer",
                panel="",
                hashed_password="original-hash",
                telegram_id=123,
                is_active=True,
                traffic=1000,
            )
        )
        session.add(
            TelegramBots(
                id=1,
                name="<My Bot>",
                url="https://bot.test",
                created_at=datetime(2025, 1, 1),
                admin_id=1,
                is_active=True,
                owner_key="owner",
                manager_key="manager",
            )
        )
        session.commit()
    hosting.initialize()
    yield ledger, factory
    engine.dispose()


def sql(ledger, query, args=()):
    with closing(ledger._connect()) as conn, conn:
        return [dict(row) for row in conn.execute(query, args)]


def quote(now=NOW):
    return hosting.Quote(Decimal("2907605"), now)


def enroll_and_issue(ledger, now=NOW):
    hosting.set_enabled(1, True, now)
    return hosting.issue(1, quote(now), now)


class FakeBot:
    def __init__(self, fail=False):
        self.sent = []
        self.fail = fail

    async def send_message(self, chat_id, text, **kwargs):
        if self.fail and chat_id == 123:
            raise RuntimeError("blocked chat")
        self.sent.append((chat_id, text, kwargs))


def test_existing_bot_is_opt_in_and_schema_upgrade_preserves_invoice(shared_db):
    ledger, _ = shared_db
    invoice = ledger.create_invoice(
        telegram_id=123, amount=10, description="old", due_at=None
    )
    ledger.init_db()
    ledger.init_db()
    state = hosting.list_billing()
    assert state["eur_price"] == "1.00"
    assert state["bots"][0]["enabled"] is False
    assert hosting.due_ids(NOW) == []
    assert ledger.get_invoice(invoice).amount == 10


def test_invoice_freezes_rate_and_price_without_granting_traffic(shared_db):
    ledger, _ = shared_db
    invoice_id = enroll_and_issue(ledger)
    invoice = ledger.get_invoice(invoice_id)
    assert invoice.amount == 291000  # euro rate rounds up to the next 1000 tomans
    assert invoice.admin_username == "buyer"
    assert invoice.traffic_gb == 0
    assert invoice.due_at is None
    period = sql(ledger, "SELECT * FROM maintenance_periods")[0]
    assert period["source"] == "PriceDB / TGJU"
    assert period["rate_irr"] == "2907605"
    assert period["rate_toman"] == 291000
    assert hosting.parse(period["period_end"]).astimezone(hosting.TEHRAN).day == 28
    hosting.set_price("2.50")
    assert ledger.get_invoice(invoice_id).amount == 291000
    next_time = hosting.anniversary(NOW, 1)
    second = hosting.issue(1, quote(next_time), next_time)
    assert ledger.get_invoice(second).amount == 727500
    assert hosting.list_billing()["bots"][0]["latest_invoice"]["invoice_id"] == second


@pytest.mark.parametrize(
    "value",
    ["0", "-1", "NaN", "Infinity", "10000.01", "0.001", "1.234", "abc", "1" * 100],
)
def test_invalid_price_does_not_change_settings(shared_db, value):
    with pytest.raises(ValueError):
        hosting.set_price(value)
    assert hosting.list_billing()["eur_price"] == "1.00"


def test_anniversaries_keep_original_day_and_leap_year():
    feb = hosting.anniversary(NOW, 1)
    march = hosting.anniversary(NOW, 2)
    assert feb.astimezone(hosting.TEHRAN).day == 28
    assert march.astimezone(hosting.TEHRAN).day == 31
    leap = NOW.replace(year=2028)
    assert hosting.anniversary(leap, 1).astimezone(hosting.TEHRAN).day == 29
    assert hosting.current_period(NOW, feb - timedelta(seconds=1))[0] == NOW
    assert hosting.current_period(NOW, feb)[0] == feb
    december = NOW.replace(month=12)
    assert hosting.anniversary(december, 1).year == 2027


def test_concurrent_retries_issue_one_invoice(shared_db):
    ledger, _ = shared_db
    hosting.set_enabled(1, True, NOW)
    with ThreadPoolExecutor(max_workers=4) as pool:
        ids = list(pool.map(lambda _: hosting.issue(1, quote(), NOW), range(8)))
    assert len([i for i in ids if i]) == 1
    assert len(sql(ledger, "SELECT * FROM invoices")) == 1
    assert len(sql(ledger, "SELECT * FROM maintenance_periods")) == 1


@pytest.mark.parametrize("status", ["pending", "paid", "cancelled"])
def test_disable_reenable_never_duplicates_period(shared_db, status):
    ledger, _ = shared_db
    invoice = enroll_and_issue(ledger)
    sql(ledger, "UPDATE invoices SET status = ? WHERE id = ?", (status, invoice))
    hosting.set_enabled(1, False, NOW + timedelta(days=2))
    hosting.set_enabled(1, True, NOW + timedelta(days=3))
    assert hosting.issue(1, quote(), NOW + timedelta(days=3)) is None
    assert len(sql(ledger, "SELECT * FROM invoices")) == 1
    assert ledger.get_invoice(invoice).status == status


def test_catchup_bills_current_month_and_records_skipped_periods(shared_db):
    ledger, _ = shared_db
    enroll_and_issue(ledger)
    future = hosting.anniversary(NOW, 4) + timedelta(days=2)
    second = hosting.issue(1, quote(future), future)
    periods = sql(ledger, "SELECT * FROM maintenance_periods ORDER BY invoice_id")
    assert len(periods) == 2
    assert periods[-1]["skipped_periods"] == 3
    assert hosting.parse(periods[-1]["period_start"]) == hosting.anniversary(NOW, 4)
    assert second == periods[-1]["invoice_id"]
    assert len(sql(ledger, "SELECT * FROM maintenance_notices")) == 1


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE telegram_bots SET is_active = 0 WHERE id = 1",
        "UPDATE admins SET is_active = 0 WHERE id = 1",
        "INSERT INTO observer_admins(admin_username, marked_at) VALUES ('buyer', 'now')",
    ],
)
def test_inactive_and_observer_skip_new_charges(shared_db, query):
    ledger, _ = shared_db
    hosting.set_enabled(1, True, NOW)
    sql(ledger, query)
    assert hosting.due_ids(NOW) == []
    assert hosting.issue(1, quote(), NOW) is None
    assert not hosting.list_billing()["bots"][0]["eligible"]


@pytest.mark.parametrize(
    "query",
    [
        "UPDATE telegram_bots SET admin_id = NULL WHERE id = 1",
        "UPDATE admins SET telegram_id = NULL WHERE id = 1",
        "UPDATE admins SET telegram_id = 456 WHERE id = 1",
        "UPDATE admins SET username = 'other' WHERE id = 1",
        "UPDATE telegram_bots SET created_at = '2026-01-01' WHERE id = 1",
        "DELETE FROM telegram_bots WHERE id = 1",
    ],
)
def test_identity_changes_prevent_charging_from_stale_due_list(shared_db, query):
    ledger, _ = shared_db
    hosting.set_enabled(1, True, NOW)
    assert hosting.due_ids(NOW) == [1]
    sql(ledger, query)
    assert hosting.issue(1, quote(), NOW) is None
    hosting.due_ids(NOW)
    assert (
        sql(ledger, "SELECT enabled FROM maintenance_subscriptions")[0]["enabled"] == 0
    )


def test_reassignment_in_orm_disables_billing_atomically(shared_db):
    ledger, factory = shared_db
    hosting.set_enabled(1, True, NOW)
    with factory() as session:
        bot = session.get(TelegramBots, 1)
        crud.update_bot(session, bot, admin_id=None)
        # Switching back before the next tick must still require explicit opt-in.
        crud.update_bot(session, bot, admin_id=1)
    assert not hosting.list_billing()["bots"][0]["enabled"]


def test_address_edit_requires_opt_in_but_preserves_paid_period(shared_db):
    ledger, factory = shared_db
    invoice = enroll_and_issue(ledger)
    with factory() as session:
        crud.update_bot(session, session.get(TelegramBots, 1), url="https://new.test")
    assert not hosting.list_billing()["bots"][0]["enabled"]
    hosting.set_enabled(1, True, NOW + timedelta(days=1))
    assert hosting.issue(1, quote(), NOW + timedelta(days=1)) is None
    assert ledger.get_invoice(invoice).status == "pending"


def test_new_owner_has_separate_subscription_and_old_invoice_stays_with_buyer(
    shared_db,
):
    ledger, factory = shared_db
    old = enroll_and_issue(ledger)
    with factory() as session:
        session.add(
            Admins(
                id=2,
                username="new-buyer",
                panel="",
                hashed_password="hash",
                is_active=True,
                telegram_id=456,
            )
        )
        session.commit()
        crud.update_bot(session, session.get(TelegramBots, 1), admin_id=2)
    hosting.set_enabled(1, True, NOW + timedelta(days=1))
    new = hosting.issue(1, quote(), NOW + timedelta(days=1))
    assert ledger.get_invoice(old).telegram_id == 123
    assert ledger.get_invoice(new).telegram_id == 456


def test_delivery_retries_same_invoice_and_deadline_starts_after_success(shared_db):
    ledger, _ = shared_db
    invoice = enroll_and_issue(ledger)
    blocked = FakeBot(fail=True)
    asyncio.run(hosting.deliver(blocked, NOW))
    assert ledger.get_invoice(invoice).due_at is None
    assert hosting._claim("maintenance_periods", NOW + timedelta(seconds=59)) is None
    success = FakeBot()
    delivered_at = NOW + timedelta(minutes=1)
    asyncio.run(hosting.deliver(success, delivered_at))
    assert len(success.sent) == 1
    assert "&lt;My Bot&gt;" in success.sent[0][1]
    assert hosting.parse(
        ledger.get_invoice(invoice).due_at
    ) == delivered_at + timedelta(days=3)
    asyncio.run(hosting.deliver(success, delivered_at + timedelta(minutes=1)))
    assert len(success.sent) == 1
    assert len(sql(ledger, "SELECT * FROM invoices")) == 1


def test_delivery_claim_survives_restart_and_expires(shared_db):
    ledger, _ = shared_db
    enroll_and_issue(ledger)
    first = hosting._claim("maintenance_periods", NOW)
    assert first
    assert hosting._claim("maintenance_periods", NOW + timedelta(minutes=4)) is None
    second = hosting._claim("maintenance_periods", NOW + timedelta(minutes=6))
    assert second and second["token"] != first["token"]
    hosting._finish("maintenance_periods", first, NOW, None)
    assert ledger.get_invoice(first["invoice_id"]).due_at is None
    hosting._finish("maintenance_periods", second, NOW + timedelta(minutes=6), None)
    assert ledger.get_invoice(first["invoice_id"]).due_at is not None


def test_paid_or_cancelled_bill_not_delivered(shared_db):
    ledger, _ = shared_db
    invoice = enroll_and_issue(ledger)
    ledger.cancel_invoice(invoice)
    bot = FakeBot()
    asyncio.run(hosting.deliver(bot, NOW))
    assert bot.sent == []


def valid_payloads():
    return (
        {"success": True, "price": 2907600, "time": hosting.stamp(NOW)},
        {
            "success": True,
            "status": "ok",
            "lastRunOk": True,
            "latestDataAt": hosting.stamp(NOW),
            "lastSuccessAt": hosting.stamp(NOW),
        },
    )


@pytest.mark.parametrize(
    "invalid",
    ["zero", "negative", "nan", "stale", "future", "unhealthy", "missing", "list"],
)
def test_bad_rate_is_rejected(invalid):
    body, health = valid_payloads()
    if invalid == "zero":
        body["price"] = 0
    if invalid == "negative":
        body["price"] = -100
    if invalid == "nan":
        body["price"] = "NaN"
    if invalid == "stale":
        body["time"] = hosting.stamp(NOW - timedelta(hours=73))
    if invalid == "future":
        body["time"] = hosting.stamp(NOW + timedelta(minutes=10))
    if invalid == "unhealthy":
        health["status"] = "stale"
    if invalid == "missing":
        body.pop("time")
    if invalid == "list":
        body = []
    with pytest.raises(ValueError):
        hosting.validate_quote(body, health, NOW)


def test_healthy_weekend_quote_is_accepted():
    body, health = valid_payloads()
    body["time"] = hosting.stamp(NOW - timedelta(hours=48))
    assert hosting.validate_quote(body, health, NOW).rate_irr == 2907600


def test_http_provider_request_and_schema(monkeypatch):
    body, health = valid_payloads()
    seen = []

    def respond(request):
        assert request.headers["User-Agent"].startswith("MIT-Panel/")
        assert request.headers["Accept"] == "application/json"
        seen.append(str(request.url))
        return httpx.Response(
            200, json=health if request.url.path.endswith("health") else body
        )

    client = httpx.AsyncClient
    monkeypatch.setattr(
        hosting.httpx,
        "AsyncClient",
        lambda **kw: client(transport=httpx.MockTransport(respond), **kw),
    )
    assert asyncio.run(hosting.fetch_quote(NOW)).rate_irr == 2907600
    assert set(seen) == {hosting.RATE_URL, hosting.HEALTH_URL}


def test_rate_outage_does_not_issue_or_advance_and_uses_persistent_backoff(
    shared_db, monkeypatch
):
    ledger, _ = shared_db
    hosting.set_enabled(1, True, NOW)
    fetch = AsyncMock(side_effect=httpx.ConnectTimeout("offline"))
    monkeypatch.setattr(hosting, "fetch_quote", fetch)
    asyncio.run(hosting.tick(FakeBot(), NOW))
    assert sql(ledger, "SELECT * FROM invoices") == []
    assert hosting.due_ids(NOW) == [1]
    asyncio.run(hosting.tick(FakeBot(), NOW + timedelta(seconds=30)))
    assert fetch.await_count == 1
    asyncio.run(hosting.tick(FakeBot(), NOW + timedelta(minutes=1)))
    assert fetch.await_count == 2
    assert len(sql(ledger, "SELECT * FROM maintenance_notices")) == 1
    monkeypatch.setattr(
        hosting,
        "fetch_quote",
        AsyncMock(return_value=quote(NOW + timedelta(minutes=3))),
    )
    asyncio.run(hosting.tick(FakeBot(), NOW + timedelta(minutes=3)))
    assert len(sql(ledger, "SELECT * FROM invoices")) == 1
    assert hosting.rate_allowed(NOW + timedelta(minutes=3))


def test_delivered_invoice_enters_existing_lock_rules_and_payment_unlocks(
    shared_db, monkeypatch
):
    ledger, factory = shared_db
    old = hosting.utcnow() - timedelta(days=4)
    invoice = enroll_and_issue(ledger, old)
    assert "buyer" not in access_lock._obligated()
    asyncio.run(hosting.deliver(FakeBot(), old))
    assert "buyer" in access_lock._obligated()
    monkeypatch.setattr(
        access_lock.bot_config.__class__, "superadmin_id_list", property(lambda _: [])
    )
    asyncio.run(access_lock.tick(FakeBot()))
    assert ledger.get_admin_lock("buyer") is not None
    request = ledger.create_request(
        admin_telegram_id=123,
        admin_username="buyer",
        requested_gb=0,
        toman_amount=ledger.get_invoice(invoice).amount,
        receipt_path="",
        kind="invoice",
        invoice_id=invoice,
    )
    topup = AsyncMock()
    monkeypatch.setattr(approvals.panel_client, "topup", topup)
    outcome = asyncio.run(approvals.approve_request(FakeBot(), request, 999))
    assert outcome.ok
    assert ledger.get_invoice(invoice).status == "paid"
    assert ledger.get_admin_lock("buyer") is None
    assert topup.await_count == 0
    with factory() as session:
        assert session.get(Admins, 1).traffic == 1000
    assert len(sql(ledger, "SELECT * FROM sales WHERE method = 'invoice'")) == 1
    assert not asyncio.run(approvals.approve_request(FakeBot(), request, 999)).ok


def test_api_requires_superadmin_and_validates_input(shared_db, monkeypatch):
    from backend.app import app
    from backend.auth.auth import get_current_admin
    from backend.api.bots import maintenance as api

    monkeypatch.setattr(api, "is_running", lambda: True)
    client = TestClient(app)
    prefix = "/dashboard/sales-bots/maintenance"
    app.dependency_overrides[get_current_admin] = lambda: {
        "role": "admin",
        "username": "buyer",
    }
    try:
        assert client.get(prefix).status_code == 403
        assert client.put(prefix + "/price", json={"eur_price": "2"}).status_code == 403
        assert client.put(prefix + "/1", json={"enabled": True}).status_code == 403
        app.dependency_overrides[get_current_admin] = lambda: {"role": "superadmin"}
        assert client.get(prefix).json()["data"]["bots"][0]["enabled"] is False
        assert (
            client.put(prefix + "/price", json={"eur_price": "2.25"}).status_code == 200
        )
        assert (
            client.put(prefix + "/price", json={"eur_price": "NaN"}).status_code == 400
        )
        assert client.put(prefix + "/1", json={"enabled": "false"}).status_code == 422
        assert client.put(prefix + "/1", json={"enabled": True}).status_code == 200
        monkeypatch.setattr(api, "is_running", lambda: False)
        assert client.put(prefix + "/1", json={"enabled": True}).status_code == 409
        assert client.put(prefix + "/1", json={"enabled": False}).status_code == 200
        assert client.put(prefix + "/987", json={"enabled": False}).status_code == 400
    finally:
        app.dependency_overrides.pop(get_current_admin, None)


def test_telegram_unauthorized_callbacks_do_not_touch_billing(shared_db, monkeypatch):
    from backend.bot.routers import maintenance as router

    monkeypatch.setattr(router, "bot_config", SimpleNamespace(superadmin_id_list=[999]))
    call = SimpleNamespace(from_user=SimpleNamespace(id=123), data="maint_set:1:1")
    asyncio.run(router.toggle(call))
    assert not hosting.list_billing()["bots"][0]["enabled"]
    assert (
        texts.BTN_BOT_MAINTENANCE
        in __import__("backend.bot.nav", fromlist=["ALL_MENU_TEXTS"]).ALL_MENU_TEXTS
    )


def test_failed_transaction_leaves_no_invoice_or_advanced_schedule(
    shared_db, monkeypatch
):
    ledger, _ = shared_db
    hosting.set_enabled(1, True, NOW)
    insert = ledger.insert_invoice

    def fail_after_insert(*args, **kwargs):
        insert(*args, **kwargs)
        raise RuntimeError("simulated disk failure")

    monkeypatch.setattr(ledger, "insert_invoice", fail_after_insert)
    with pytest.raises(RuntimeError):
        hosting.issue(1, quote(), NOW)
    assert sql(ledger, "SELECT * FROM invoices") == []
    assert sql(ledger, "SELECT * FROM maintenance_periods") == []
    assert hosting.due_ids(NOW) == [1]


def test_two_bots_for_same_person_are_charged_independently(shared_db):
    ledger, factory = shared_db
    with factory() as session:
        session.add(
            TelegramBots(
                id=2,
                name="second",
                url="https://second.test",
                created_at=datetime(2025, 1, 1),
                admin_id=1,
                is_active=True,
                owner_key="x",
                manager_key="y",
            )
        )
        session.commit()
    first = enroll_and_issue(ledger)
    hosting.set_enabled(2, True, NOW)
    second = hosting.issue(2, quote(), NOW)
    assert first != second
    assert (
        ledger.get_invoice(first).telegram_id
        == ledger.get_invoice(second).telegram_id
        == 123
    )
    assert len(sql(ledger, "SELECT * FROM invoices")) == 2


def test_opt_out_does_not_fetch_rate_or_send_messages(shared_db, monkeypatch):
    fetch = AsyncMock()
    monkeypatch.setattr(hosting, "fetch_quote", fetch)
    bot = FakeBot()
    asyncio.run(hosting.tick(bot, NOW))
    assert fetch.await_count == 0
    assert bot.sent == []


def test_missing_owner_cannot_enable_billing(shared_db):
    ledger, _ = shared_db
    sql(ledger, "UPDATE telegram_bots SET admin_id = NULL WHERE id = 1")
    with pytest.raises(ValueError, match=texts.MAINT_INELIGIBLE):
        hosting.set_enabled(1, True, NOW)
    assert sql(ledger, "SELECT * FROM maintenance_subscriptions") == []


@pytest.mark.parametrize("field", ["time", "latestDataAt", "lastSuccessAt"])
def test_null_timestamps_are_rejected(field):
    body, health = valid_payloads()
    (body if field == "time" else health)[field] = None
    with pytest.raises(ValueError):
        hosting.validate_quote(body, health, NOW)


def test_calendar_uses_tehran_day_rather_than_utc_day():
    anchor = datetime(2026, 1, 31, 22, 0, tzinfo=timezone.utc)  # Feb 1 in Tehran
    next_month = hosting.anniversary(anchor, 1).astimezone(hosting.TEHRAN)
    assert (next_month.month, next_month.day, next_month.hour) == (3, 1, 1)


def test_owner_deletion_keeps_invoice_history_but_disables_future_charges(shared_db):
    ledger, factory = shared_db
    invoice = enroll_and_issue(ledger)
    with factory() as session:
        assert crud.remove_admin(session, 1)
    assert not hosting.list_billing()["bots"][0]["enabled"]
    assert ledger.get_invoice(invoice).telegram_id == 123
    assert hosting.due_ids(hosting.anniversary(NOW, 1)) == []


def test_existing_reminders_escape_hosting_bot_name(shared_db):
    ledger, _ = shared_db
    from backend.bot.weekly import send_invoice_reminders

    invoice = enroll_and_issue(ledger, hosting.utcnow() - timedelta(days=4))
    sql(
        ledger,
        "UPDATE invoices SET due_at = ? WHERE id = ?",
        (hosting.stamp(hosting.utcnow() - timedelta(hours=1)), invoice),
    )
    bot = FakeBot()
    assert asyncio.run(send_invoice_reminders(bot)) == 1
    assert "&lt;My Bot&gt;" in bot.sent[0][1]


def test_old_installation_without_maintenance_tables_can_still_edit_bots(shared_db):
    ledger, factory = shared_db
    sql(ledger, "DROP TABLE maintenance_subscriptions")
    with factory() as session:
        bot = session.get(TelegramBots, 1)
        assert (
            crud.update_bot(session, bot, url="https://renamed.test").url
            == "https://renamed.test"
        )


def test_disabling_during_rate_fetch_is_rechecked_before_invoice(
    shared_db, monkeypatch
):
    ledger, _ = shared_db
    hosting.set_enabled(1, True, NOW)

    async def disabled_in_flight(now):
        hosting.set_enabled(1, False, now)
        return quote(now)

    monkeypatch.setattr(hosting, "fetch_quote", disabled_in_flight)
    asyncio.run(hosting.tick(FakeBot(), NOW))
    assert sql(ledger, "SELECT * FROM invoices") == []


def test_legacy_bot_without_creation_timestamp_can_be_enrolled(shared_db):
    ledger, _ = shared_db
    sql(ledger, "UPDATE telegram_bots SET created_at = NULL WHERE id = 1")
    invoice = enroll_and_issue(ledger)
    assert invoice
    assert hosting.list_billing()["bots"][0]["enabled"]
    assert hosting.due_ids(NOW) == []


def test_telegram_superadmin_can_manage_enrollment_and_price(shared_db, monkeypatch):
    from backend.bot.routers import maintenance as router

    monkeypatch.setattr(router, "bot_config", SimpleNamespace(superadmin_id_list=[999]))
    message = SimpleNamespace(answer=AsyncMock(), edit_reply_markup=AsyncMock())
    call = SimpleNamespace(
        from_user=SimpleNamespace(id=999),
        data="maint_set:1:1",
        answer=AsyncMock(),
        message=message,
    )
    asyncio.run(router.toggle(call))
    assert hosting.list_billing()["bots"][0]["enabled"]
    state = SimpleNamespace(set_state=AsyncMock(), clear=AsyncMock())
    asyncio.run(router.ask_price(call, state))
    price_message = SimpleNamespace(
        from_user=SimpleNamespace(id=999), text="2.50", answer=AsyncMock()
    )
    asyncio.run(router.save_price(price_message, state))
    assert hosting.list_billing()["eur_price"] == "2.50"
    assert state.clear.await_count == 1
    call.data = "maint_set:1:0"
    asyncio.run(router.toggle(call))
    assert not hosting.list_billing()["bots"][0]["enabled"]



@pytest.mark.parametrize(
    "rate_irr, expected",
    [
        ("3657600", 366000),
        ("3660000", 366000),
        ("3660001", 367000),
        ("3650000", 365000),
        ("3659999", 366000),
    ],
)
def test_euro_rate_rounds_up_to_thousand_tomans(shared_db, rate_irr, expected):
    ledger, _ = shared_db
    hosting.set_enabled(1, True, NOW)
    invoice_id = hosting.issue(1, hosting.Quote(Decimal(rate_irr), NOW), NOW)
    assert ledger.get_invoice(invoice_id).amount == expected
    period = sql(ledger, "SELECT * FROM maintenance_periods")[0]
    assert period["rate_irr"] == rate_irr
    assert period["rate_toman"] == expected


def test_round_euro_rate_before_multiplying_by_monthly_fee(shared_db):
    ledger, _ = shared_db
    hosting.set_price("1.25")
    hosting.set_enabled(1, True, NOW)
    invoice_id = hosting.issue(1, hosting.Quote(Decimal("3657600"), NOW), NOW)
    assert ledger.get_invoice(invoice_id).amount == 457500  # 366000 * 1.25
    assert sql(ledger, "SELECT rate_toman FROM maintenance_periods")[0]["rate_toman"] == 366000


def test_customer_invoice_omits_rate_source_and_conversion_details(shared_db):
    ledger, _ = shared_db
    invoice_id = enroll_and_issue(ledger)
    bot = FakeBot()
    asyncio.run(hosting.deliver(bot, NOW))
    message = next(text for chat_id, text, _ in bot.sent if chat_id == 123)
    assert f"#{invoice_id}" in message
    assert "&lt;My Bot&gt;" in message
    assert "291,000" in message
    assert "دوره:" in message
    assert "مهلت پرداخت:" in message
    for detail in ("PriceDB", "TGJU", "منبع", "یورو", "ریال", "زمان نرخ"):
        assert detail not in message
        assert detail not in ledger.get_invoice(invoice_id).description


def test_rate_snapshot_upgrade_keeps_old_invoice_amounts(shared_db):
    ledger, _ = shared_db
    invoice_id = enroll_and_issue(ledger)
    # Simulate the previous release, which has no applied-rate snapshot column.
    sql(ledger, "ALTER TABLE maintenance_periods DROP COLUMN rate_toman")
    sql(ledger, "UPDATE invoices SET amount = 290761 WHERE id = ?", (invoice_id,))
    ledger.init_db()
    ledger.init_db()
    assert ledger.get_invoice(invoice_id).amount == 290761
    assert sql(ledger, "SELECT rate_toman FROM maintenance_periods")[0]["rate_toman"] is None
    hosting.set_enabled(1, False, NOW + timedelta(days=1))
    hosting.set_enabled(1, True, NOW + timedelta(days=2))
    assert hosting.issue(1, quote(), NOW + timedelta(days=2)) is None
