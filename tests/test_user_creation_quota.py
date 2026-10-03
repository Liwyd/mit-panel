"""A user may never be created without a traffic quota.

`ClientInput.total` declares `ge=104857600`, but pydantic does not validate
defaults: the field used to default to `0.0`, a request omitting it was
accepted as-is, and Marzban reads `data_limit = 0` as "no limit" — so leaving
the field out handed out unlimited traffic below the floor the constraint
claims to enforce.  `ClientUpdateInput.total` has always been required; create
now matches it.
"""

import pytest
from pydantic import ValidationError

from backend.schema._input import ClientInput


def _payload(**overrides):
    payload = {"email": "user", "id": "uuid", "expiry_time": 0, "sub_id": "s"}
    payload.update(overrides)
    return payload


def test_omitting_the_quota_is_refused():
    with pytest.raises(ValidationError):
        ClientInput(**_payload())


def test_a_quota_below_the_floor_is_refused():
    with pytest.raises(ValidationError):
        ClientInput(**_payload(total=50 * 1024**2))


def test_the_declared_floor_still_passes():
    client = ClientInput(**_payload(total=104857600))
    assert client.total == 104857600
