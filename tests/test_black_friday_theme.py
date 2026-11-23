"""The temporary Black Friday theme: its public state and its end date."""

from datetime import datetime, timedelta, timezone

import pytest
from pydantic import ValidationError

from backend.schema._input import SettingsInput
from backend.utils import settings_store as store


def _state(**overrides):
    data = dict(store.DEFAULTS)
    data.update(overrides)
    return store.black_friday_state(data)


def test_off_by_default():
    assert _state()["active"] is False


def test_active_until_end():
    future = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    state = _state(black_friday_enabled=True, black_friday_ends_at=future)
    assert state["active"] is True
    assert state["ends_at"] is not None


def test_switches_itself_off_after_end():
    past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
    assert _state(black_friday_enabled=True, black_friday_ends_at=past)["active"] is False


def test_naive_end_is_tehran_time():
    end = store.parse_black_friday_end("2026-11-30T23:59:59")
    assert end.utcoffset() == timedelta(hours=3, minutes=30)


def test_bad_end_keeps_theme_off():
    assert _state(black_friday_enabled=True, black_friday_ends_at="soon")["active"] is False


def test_public_branding_carries_state():
    assert "black_friday" in store.get_public_branding()


def test_settings_input_rejects_bad_date():
    with pytest.raises(ValidationError):
        SettingsInput(black_friday_ends_at="next friday")
    assert SettingsInput(black_friday_ends_at=" 2026-11-30T23:59:59+03:30 ").black_friday_ends_at == "2026-11-30T23:59:59+03:30"
