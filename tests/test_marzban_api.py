"""The Marzban client must not hang, must not lie about an empty panel, and
must page through the full user list.

Every call used to be made without a timeout: one unreachable panel blocked
the event loop indefinitely.  `get_inbounds` used to return whatever came
back — including `{}` — which is how panels ended up persisted with no inbound
set at all.  The user list used to be fetched in one unpaginated call, so
panels with more users than a single page return would look almost empty.
"""

import asyncio
from datetime import datetime, timedelta, timezone

import requests

import pytest

from backend.services.marzban import api as marzban_api
from backend.services.marzban.api import APIService, MarzbanAPIError


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class FakeSession:
    """Records every request's kwargs and replays scripted responses."""

    def __init__(self, script):
        self.script = list(script)
        self.calls = []

    def _respond(self, method, url, kwargs):
        self.calls.append({"method": method, "url": url, **kwargs})
        if not self.script:
            return FakeResponse(payload={})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        return step

    def get(self, url, **kwargs):
        return self._respond("GET", url, kwargs)

    def post(self, url, **kwargs):
        return self._respond("POST", url, kwargs)

    def put(self, url, **kwargs):
        return self._respond("PUT", url, kwargs)

    def delete(self, url, **kwargs):
        return self._respond("DELETE", url, kwargs)


async def _noop_login(self):
    self.token = "test-token"
    self.headers = {"Authorization": "Bearer test-token"}


@pytest.fixture(autouse=True)
def patched_login(monkeypatch):
    monkeypatch.setattr(APIService, "_login", _noop_login)
    monkeypatch.setattr(APIService, "_token_cache", {})


def service(script=()) -> tuple[APIService, FakeSession]:
    svc = APIService(url="http://panel.test", username="sudo", password="pw")
    session = FakeSession(script)
    svc.session = session
    return svc, session


def test_inbounds_survive_a_flaky_read():
    svc, session = service(
        [
            FakeResponse(status_code=503, text="busy"),
            FakeResponse(payload={"vless": [{"tag": "vless-1"}]}),
        ]
    )

    result = asyncio.run(svc.get_inbounds())

    assert result == {"vless": ["vless-1"]}
    assert len(session.calls) == 2


def test_inbounds_raise_after_the_last_retry_instead_of_returning_empty():
    svc, session = service(
        [FakeResponse(status_code=500, text="boom")] * 3
    )

    with pytest.raises(MarzbanAPIError, match="inbounds"):
        asyncio.run(svc.get_inbounds())

    assert len(session.calls) == 3


def test_a_panel_with_no_inbounds_is_an_error_not_an_empty_dict():
    svc, _ = service([FakeResponse(payload={"vless": []})])

    with pytest.raises(MarzbanAPIError, match="no inbounds"):
        asyncio.run(svc.get_inbounds())


def test_malformed_payload_is_reported_as_an_error():
    svc, _ = service([FakeResponse(payload={"detail": "not allowed"})])

    with pytest.raises(MarzbanAPIError):
        asyncio.run(svc.get_inbounds())


def test_every_request_carries_a_timeout():
    """One unreachable panel must not freeze the whole event loop."""
    svc, session = service([FakeResponse(payload={"users": [], "total": 0})])

    asyncio.run(svc.get_users_page())

    assert session.calls[0]["timeout"] == marzban_api.REQUEST_TIMEOUT


def test_user_pages_stop_at_the_reported_total():
    def page(offset, users):
        return FakeResponse(payload={"total": 3, "users": users})

    svc, session = service(
        [
            page(0, [{"username": "a"}, {"username": "b"}]),
            page(2, [{"username": "c"}]),
        ]
    )

    users = asyncio.run(svc.get_all_users_paginated(page_size=2))

    assert [u["username"] for u in users] == ["a", "b", "c"]
    assert [c["params"]["offset"] for c in session.calls] == [0, 2]


def test_a_partial_read_aborts_instead_of_reporting_a_mass_deletion():
    """A caller that only sees page one must not conclude every user left."""
    svc, session = service(
        [
            FakeResponse(payload={"total": 10, "users": [{"username": "a"}]}),
            FakeResponse(payload={"total": 10, "users": []}),
        ]
    )

    with pytest.raises(MarzbanAPIError, match="Incomplete"):
        asyncio.run(svc.get_all_users_paginated(page_size=1))

    assert len(session.calls) == 2


def test_a_server_that_ignores_offset_does_not_loop_forever():
    first_page = FakeResponse(
        payload={"total": 100, "users": [{"username": "a"}] * 50}
    )
    svc, session = service([first_page, first_page, first_page])

    with pytest.raises(MarzbanAPIError, match="offset"):
        asyncio.run(svc.get_all_users_paginated(page_size=50))

    assert len(session.calls) <= 3


def test_nodes_status_normalises_marzban_enum():
    """The dashboard maps these straight onto its Connected/Error/Disabled
    badges, so an unexpected value must not reach the UI as-is."""
    svc, session = service(
        [
            FakeResponse(
                payload=[
                    {"id": 1, "name": "eu-1", "status": "connected", "message": None},
                    {"id": 2, "name": "de-2", "status": "ERROR", "message": "refused"},
                    {"id": 3, "name": "fr-3", "status": None},
                    {"id": 4, "name": "es-4", "status": "disabled", "message": None},
                    {"id": 5, "name": "us-5", "status": "Online"},
                ]
            )
        ]
    )

    nodes = asyncio.run(svc.get_nodes_status())

    assert [(n["id"], n["status"]) for n in nodes] == [
        (1, "connected"),
        (2, "error"),
        (3, "unknown"),
        (4, "disabled"),
        (5, "unknown"),
    ]
    assert session.calls[0]["timeout"] == marzban_api.REQUEST_TIMEOUT


def test_nodes_status_degrades_to_empty_instead_of_failing_the_dashboard():
    """`marzban_overview` already expects to be able to call this on panels
    that do not expose /api/nodes at all."""
    svc, _ = service([FakeResponse(status_code=404, text="not found")])

    assert asyncio.run(svc.get_nodes_status()) == []


def test_nodes_status_ignores_non_list_payloads():
    svc, _ = service([FakeResponse(payload={"detail": "oops"})])

    assert asyncio.run(svc.get_nodes_status()) == []


class _TokenResponse:
    def __init__(self, status_code, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} for token")


def test_verify_credentials_false_only_when_marzban_rejects(monkeypatch):
    monkeypatch.setattr(
        marzban_api.requests, "post", lambda *a, **k: _TokenResponse(401, {})
    )
    svc, _ = service()

    assert asyncio.run(svc.verify_credentials()) is False


def test_verify_credentials_raises_when_the_panel_cannot_be_asked(monkeypatch):
    """The whole point: an unreachable panel must not be reported as a wrong
    password, so the caller's 502 branch has to be reachable."""
    def boom(*a, **k):
        raise requests.ConnectionError("refused")

    monkeypatch.setattr(marzban_api.requests, "post", boom)
    svc, _ = service()

    with pytest.raises(requests.ConnectionError):
        asyncio.run(svc.verify_credentials())


def test_verify_credentials_raises_on_a_server_side_failure(monkeypatch):
    monkeypatch.setattr(
        marzban_api.requests, "post", lambda *a, **k: _TokenResponse(503, {})
    )
    svc, _ = service()

    with pytest.raises(requests.HTTPError):
        asyncio.run(svc.verify_credentials())


def test_verify_credentials_accepts_a_real_token(monkeypatch):
    seen = {}

    def post(url, **kwargs):
        seen.update(kwargs)
        return _TokenResponse(200, {"access_token": "t"})

    monkeypatch.setattr(marzban_api.requests, "post", post)
    svc, _ = service()

    assert asyncio.run(svc.verify_credentials()) is True
    assert seen["timeout"] == marzban_api.REQUEST_TIMEOUT


def _seen(seconds_ago: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=seconds_ago)).isoformat()


def _user_page(users):
    return FakeResponse(payload={"total": 999, "users": users})


def test_online_count_reads_past_the_first_page():
    """The old unpaginated call sent no `limit`, so Marzban answered with its
    default page size and everyone past page one was counted offline."""
    svc, session = service(
        [
            _user_page([{"online_at": _seen(5)}, {"online_at": _seen(10)}]),
            _user_page([{"online_at": _seen(15)}]),
        ]
    )

    count = asyncio.run(svc.count_online_users(page_size=2))

    assert count == 3
    assert [c["params"]["offset"] for c in session.calls] == [0, 2]
    assert all(c["params"]["limit"] == 2 for c in session.calls)
    assert all(c["timeout"] == marzban_api.REQUEST_TIMEOUT for c in session.calls)


def test_online_count_stops_at_the_first_seen_older_than_the_window():
    """Sorted newest-first, so the first out-of-window user ends the scan."""
    svc, session = service(
        [
            _user_page(
                [
                    {"online_at": _seen(5)},
                    {"online_at": _seen(9999)},
                    {"online_at": _seen(6)},
                ]
            )
        ]
    )

    count = asyncio.run(svc.count_online_users(window_seconds=60, page_size=3))

    assert count == 1
    assert len(session.calls) == 1


def test_online_count_falls_back_when_the_sort_field_is_rejected():
    """Some Marzban builds answer 400 to `sort=-online_at`. The retry is the
    same page, and nothing has been counted yet, so it cannot double count."""
    svc, session = service(
        [
            FakeResponse(status_code=400, payload={"detail": "sort"}),
            _user_page([{"online_at": _seen(5)}, {"online_at": _seen(6)}]),
        ]
    )

    count = asyncio.run(svc.count_online_users(page_size=2))

    assert count == 2
    assert session.calls[0]["params"]["sort"] == "-online_at"
    assert "sort" not in session.calls[1]["params"]


def test_online_count_is_bounded_so_a_huge_panel_cannot_stall_the_request():
    """Every page full of fresh users and never a short page: the cap is the
    only thing that ends this scan."""
    full = [{"online_at": _seen(5)}] * 2
    svc, session = service([_user_page(full)] * 10)

    asyncio.run(svc.count_online_users(page_size=2, max_pages=3))

    assert len(session.calls) == 3


def test_online_count_treats_a_bad_timestamp_as_offline():
    svc, _ = service([_user_page([{"online_at": "not-a-date"}, {"online_at": None}])])

    assert asyncio.run(svc.count_online_users(page_size=5)) == 0


def test_get_admin_returns_the_filtered_record():
    """One admin should cost one request, not the whole admin list."""
    svc, session = service(
        [FakeResponse(payload=[{"username": "reseller", "is_sudo": False}])]
    )

    found = asyncio.run(svc.get_admin("reseller"))

    assert found == {"username": "reseller", "is_sudo": False}
    assert len(session.calls) == 1
    assert session.calls[0]["params"] == {"username": "reseller"}
    assert session.calls[0]["timeout"] == marzban_api.REQUEST_TIMEOUT


def test_get_admin_rechecks_the_username_against_the_full_list():
    """Builds whose filter is loose, or absent, still resolve the exact name."""
    svc, session = service(
        [
            FakeResponse(payload=[{"username": "reseller-2"}]),
            FakeResponse(
                payload=[
                    {"username": "reseller"},
                    {"username": "reseller-2"},
                ]
            ),
        ]
    )

    found = asyncio.run(svc.get_admin("reseller"))

    assert found["username"] == "reseller"
    assert len(session.calls) == 2
    assert session.calls[1]["params"] is None


def test_get_admin_reports_an_unreachable_panel_as_unreachable():
    """Returning None here would make the caller answer "no such admin" for a
    panel that is simply down."""
    svc, _ = service([requests.ConnectionError("refused")])

    with pytest.raises(requests.ConnectionError):
        asyncio.run(svc.get_admin("reseller"))


def test_a_password_change_drops_that_admins_cached_token():
    """verify_credentials() logs the target admin in first, so a token for the
    password that is about to stop working is sitting in the cache."""
    svc, session = service(
        [
            FakeResponse(payload=[{"username": "reseller", "is_sudo": False}]),
            FakeResponse(status_code=200),
        ]
    )
    stale_key = f"{svc.url}|reseller"
    APIService._token_cache[stale_key] = ("old-token", 0.0)

    status = asyncio.run(svc.update_admin_password("reseller", "new-password"))

    assert status == 200
    assert stale_key not in APIService._token_cache
    assert session.calls[1]["method"] == "PUT"
