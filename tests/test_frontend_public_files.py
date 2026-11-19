"""The SPA catch-all serves the build's root files (favicon, PWA icons,
manifest) as themselves, and everything else — including traversal attempts —
as index.html."""

import importlib

from fastapi.testclient import TestClient

# `backend/__init__.py` re-exports the FastAPI object as `backend.app`, so a
# plain `import backend.app as m` binds the app, not the module.
app_module = importlib.import_module("backend.app")
from backend.config import config


def _build(tmp_path):
    (tmp_path / "index.html").write_text("<!doctype html><title>spa</title>")
    (tmp_path / "favicon.png").write_bytes(b"\x89PNG\r\n\x1a\nfake")
    (tmp_path / "manifest.webmanifest").write_text('{"name":"x"}')
    (tmp_path / "assets").mkdir()
    return tmp_path


def test_allowlist_holds_root_files_only(tmp_path):
    files = app_module._public_root_files(_build(tmp_path))
    assert set(files) == {"favicon.png", "manifest.webmanifest"}


def test_allowlist_is_empty_without_a_build(tmp_path):
    assert app_module._public_root_files(tmp_path / "missing") == {}


def _client(tmp_path, monkeypatch):
    build = _build(tmp_path)
    monkeypatch.setattr(app_module, "_public_files", app_module._public_root_files(build))
    monkeypatch.setattr(app_module, "index_html_path", build / "index.html")
    return TestClient(app_module.app)


def test_root_files_are_served_with_their_types(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    prefix = f"/{config.URLPATH}"

    r = client.get(f"{prefix}/favicon.png")
    assert r.status_code == 200
    assert r.headers["content-type"] == "image/png"
    assert r.content.startswith(b"\x89PNG")

    r = client.get(f"{prefix}/manifest.webmanifest")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/manifest+json")


def test_spa_routes_and_unknown_names_still_get_index(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    prefix = f"/{config.URLPATH}"
    for path in ("", "/", "/login", "/settings/panels", "/nope.png", "/assets/../favicon.png/x"):
        r = client.get(prefix + path)
        assert r.status_code == 200, path
        assert "spa" in r.text, path


def test_traversal_never_leaves_the_build(tmp_path, monkeypatch):
    client = _client(tmp_path, monkeypatch)
    prefix = f"/{config.URLPATH}"
    for path in ("/../pyproject.toml", "/..%2Fpyproject.toml", "/%2e%2e/pyproject.toml", "/index.html/../../.env"):
        r = client.get(prefix + path)
        assert "[project]" not in r.text, path
        assert "JWT" not in r.text, path
