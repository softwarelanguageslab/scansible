from __future__ import annotations


def ensure_not_none[T](value: T | None) -> T:
    assert value is not None
    return value
