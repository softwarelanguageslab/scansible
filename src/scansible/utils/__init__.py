"""Miscellaneous utilities."""

from __future__ import annotations


class Sentinel:
    def __repr__(self) -> str:
        return f"SENTINEL"


SENTINEL = Sentinel()
