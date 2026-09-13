"""Byte <-> GiB conversion, matching the panel's own 1024**3 convention."""

GIB = 1024**3


def gb_to_bytes(gb: float) -> int:
    return int(gb * GIB)


def bytes_to_gb(value: int | float | None) -> float:
    return (value or 0) / GIB
