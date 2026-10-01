"""The Marzban client must not hang, must not lie about an empty panel, and
must page through the full user list.

Every call used to be made without a timeout: one unreachable panel blocked
the event loop indefinitely.  `get_inbounds` used to return whatever came
back — including `{}` — which is how panels ended up persisted with no inbound
set at all.  The user list used to be fetched in one unpaginated call, so
panels with more users than a single page return would look almost empty.
"""

import asyncio

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
