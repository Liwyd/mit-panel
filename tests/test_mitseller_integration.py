"""Installing a mit-seller bot from the panel.

The panel runs in a container with no shell and no SSH, so the only way it can
get a bot installed is to ask the mit-seller server over the provisioning API
that `install.sh provisioner-setup` starts. That makes three things worth
pinning down here: the panel must never send a BotFather token over a
connection nobody has vouched for, the request it sends must carry exactly what
the server validates, and writing the reseller's panel into the bot must be
idempotent — the create endpoint refuses a second panel with the same name, so
a repeat has to update rather than fail.
"""

from __future__ import annotations

import asyncio
import json

import httpx
import pytest

from backend.bot.routers import bot_provision
from backend.utils import mitseller


@pytest.fixture()
def settings_stub(monkeypatch, tmp_path):
    """The three settings this module reads, without touching the real file."""
    data = {
        "mitseller_server": "176.124.199.78",
        "mitseller_provision_token": "a" * 64,
        "mitseller_server_cert": "-----BEGIN CERTIFICATE-----\nSANDBOX\n-----END CERTIFICATE-----",
    }
    monkeypatch.setattr(mitseller, "get_settings", lambda: dict(data))
    monkeypatch.setattr(mitseller, "DATA_DIR", str(tmp_path))
    monkeypatch.setattr(mitseller, "_CERT_PATH", str(tmp_path / "cert.pem"))
    return data


def _transport(handler):
    """Patch httpx everywhere this module (and the bot router) opens a client."""
    real = httpx.AsyncClient

    def factory(*args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        return real(*args, **kwargs)

    return factory


def _run(coro):
    return asyncio.run(coro)


# ── when the panel may ask at all ──────────────────────────────────────────


def test_provision_is_off_until_a_token_is_set(monkeypatch):
    """The address defaults to localhost, so an address on its own says
    nothing; only a token means someone has actually set this up."""
    data = {"mitseller_server": "localhost", "mitseller_provision_token": ""}
    monkeypatch.setattr(mitseller, "get_settings", lambda: dict(data))
    assert mitseller.provision_configured() is False
    data["mitseller_provision_token"] = "a" * 64
    assert mitseller.provision_configured() is True


def test_the_panel_refuses_to_send_a_token_without_a_pinned_certificate(settings_stub):
    """The address is a bare IP, so the certificate is the only thing that
    makes sending a BotFather token to it safe. Without it, refuse."""
    settings_stub["mitseller_server_cert"] = ""
    with pytest.raises(mitseller.MitSellerError, match="گواهی"):
        _run(
            mitseller.provision_bot(
                token="123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
                domain="new.example.com",
                admin_id=1,
            )
        )


def test_the_panel_refuses_when_nothing_is_configured(monkeypatch):
    monkeypatch.setattr(mitseller, "get_settings", lambda: {"mitseller_server": "", "mitseller_provision_token": ""})
    with pytest.raises(mitseller.MitSellerError, match="ثبت نشده"):
        _run(
            mitseller.provision_bot(
                token="123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
                domain="new.example.com",
                admin_id=1,
            )
        )


# ── what goes over the wire ────────────────────────────────────────────────


def test_provision_sends_what_the_server_validates(settings_stub, monkeypatch):
    """The server accepts a token, a domain and a numeric admin id and nothing
    else that could reach a shell, so that is exactly what must leave here."""
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        seen["body"] = request.content
        return httpx.Response(200, json={"ok": True, "data": {"n": 7, "url": "https://new.example.com"}})

    monkeypatch.setattr(httpx, "AsyncClient", _transport(handler))
    out = _run(
        mitseller.provision_bot(
            token="123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
            domain="new.example.com",
            admin_id=6900787101,
        )
    )
    assert seen["url"] == "https://176.124.199.78:18100/provision"
    assert seen["auth"] == f"Bearer {'a' * 64}"
    body = json.loads(seen["body"])
    assert body["token"] == "123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw"
    assert body["domain"] == "new.example.com"
    assert body["admin_id"] == "6900787101"
    assert "n" not in body  # the server picks the number
    assert out["n"] == 7


def test_provision_surfaces_what_the_server_said(settings_stub, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, json={"ok": False, "error": "domain is not a hostname"})

    monkeypatch.setattr(httpx, "AsyncClient", _transport(handler))
    with pytest.raises(mitseller.MitSellerError, match="hostname"):
        _run(
            mitseller.provision_bot(
                token="123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
                domain="new.example.com",
                admin_id=1,
            )
        )


def test_an_unreachable_server_is_reported_not_raised(settings_stub, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "AsyncClient", _transport(handler))
    with pytest.raises(mitseller.MitSellerError, match="دسترس نیست"):
        _run(
            mitseller.provision_bot(
                token="123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw",
                domain="new.example.com",
                admin_id=1,
            )
        )


# ── writing the reseller's panel into the bot (R5) ────────────────────────


def _panels_handler(store: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "GET":
            return httpx.Response(200, json={"ok": True, "data": list(store.values())})
        if request.method == "POST":
            body = json.loads(request.content)
            if body["name"] in store:
                return httpx.Response(409, json={"ok": False, "error": "a panel with this name already exists"})
            row = {"id": len(store) + 1, "name_panel": body["name"], "url_panel": body["url"],
                   "username_panel": body["username"], "password_panel": body["password"], "type": body["type"]}
            store[row["id"]] = row
            return httpx.Response(200, json={"ok": True, "data": row})
        if request.method == "PUT":
            panel_id = int(str(request.url).rstrip("/").rsplit("/", 1)[-1])
            row = store.get(panel_id)
            if row is None:
                return httpx.Response(404, json={"ok": False, "error": "panel not found"})
            body = json.loads(request.content)
            for key, column in (("url_panel", "url_panel"), ("username_panel", "username_panel"),
                                ("password_panel", "password_panel")):
                if key in body:
                    row[column] = body[key]
            return httpx.Response(200, json={"ok": True, "data": row})
        return httpx.Response(405)

    return handler


def test_the_vip_panel_is_created_the_first_time(monkeypatch):
    store: dict = {}
    monkeypatch.setattr(httpx, "AsyncClient", _transport(_panels_handler(store)))
    note = _run(
        mitseller.push_vip_panel(
            bot_url="https://new.example.com",
            owner_key="owner-key",
            username="reseller1",
            password="pass1",
            panel_url="https://marzban.test:8000",
        )
    )
    assert mitseller.VIP_PANEL_NAME in note
    assert len(store) == 1
    row = next(iter(store.values()))
    assert row["name_panel"] == "پنل VIP"
    assert row["url_panel"] == "https://marzban.test:8000"
    assert row["username_panel"] == "reseller1"
    assert row["password_panel"] == "pass1"
    assert row["type"] == "marzban"


def test_the_vip_panel_is_updated_not_duplicated_the_second_time(monkeypatch):
    """The create endpoint refuses a second panel with the same name, so a
    repeat — a bot reinstalled, an admin whose password changed — has to
    update the row that is already there."""
    store: dict = {}
    monkeypatch.setattr(httpx, "AsyncClient", _transport(_panels_handler(store)))
    call = dict(bot_url="https://new.example.com", owner_key="owner-key",
                username="reseller1", password="pass1", panel_url="https://marzban.test:8000")
    _run(mitseller.push_vip_panel(**call))
    call.update(password="a-new-password")
    _run(mitseller.push_vip_panel(**call))
    assert len(store) == 1, "a second panel row was created"
    assert next(iter(store.values()))["password_panel"] == "a-new-password"


def test_a_bot_without_a_username_is_still_wired_up():
    """An admin with no Marzban password cannot have a panel pushed; saying so
    beats silently leaving the bot empty."""
    with pytest.raises(mitseller.MitSellerError):
        _run(
            mitseller.push_vip_panel(
                bot_url="https://new.example.com",
                owner_key="owner-key",
                username="",
                password="pass1",
                panel_url="https://marzban.test:8000",
            )
        )


# ── what the panel accepts before it asks the server ───────────────────────


@pytest.mark.parametrize(
    "token,ok",
    [
        ("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw", True),
        ("555:AAAAabcdefghijklmnopqrstuvwxyz012345", True),
        ("123456789:AAHdqTcvCH1vGWJxfSeofSAs0K5PALDsaw; id", False),
        ("123456789:AAH`id`", False),
        ("123456789:AAH$(id)", False),
        ("not-a-token", False),
        ("", False),
    ],
)
def test_the_token_regex_lets_nothing_reach_a_shell(token, ok):
    assert bool(bot_provision.TOKEN_RE.match(token)) is ok


@pytest.mark.parametrize(
    "domain,ok",
    [
        ("new.example.com", True),
        ("a-b.example.com", True),
        ("OK.example.com", False),
        ("new.example.com; id", False),
        ("new.example.com evil.com", False),
        ("new.example.com$(id)", False),
        ("new.example.com/../../x", False),
        ("localhost", False),
        ("", False),
    ],
)
def test_the_domain_regex_lets_nothing_reach_a_shell(domain, ok):
    assert bool(bot_provision.DOMAIN_RE.match(domain)) is ok


def test_a_domain_with_a_double_dash_is_refused_even_if_the_regex_allows_it():
    """certbot takes anything starting with a dash as a flag, and a hostname
    may legally contain "--", so this is checked separately."""
    assert bot_provision.DOMAIN_RE.match("new.example.com--unrelated")
    assert "--" in "new.example.com--unrelated"
