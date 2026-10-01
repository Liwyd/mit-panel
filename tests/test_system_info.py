"""The dashboard's system tile is typed against these exact keys, and the
endpoint is `async def`, so this must return without blocking the event loop."""

from backend.utils.system import get_system_info

REQUIRED_KEYS = (
    "total_memory",
    "used_memory",
    "cpu_percent",
    "cpu_cores",
    "disk_total",
    "disk_used",
    "swap_total",
    "swap_used",
)


def test_system_info_reports_the_expected_shape():
    info = get_system_info()

    assert tuple(info) == REQUIRED_KEYS
    assert info["cpu_cores"] > 0
    assert 0.0 <= info["cpu_percent"] <= 100.0
    assert info["total_memory"] >= info["used_memory"]
    assert info["disk_total"] >= info["disk_used"]
