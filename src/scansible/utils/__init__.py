"""Miscellaneous utilities."""

from __future__ import annotations

from typing import TypeVar

from collections.abc import Callable, Iterable


class Sentinel:
    def __repr__(self) -> str:
        return f"SENTINEL"


SENTINEL = Sentinel()


_T = TypeVar("_T")
_K = TypeVar("_K")
_V = TypeVar("_V")


def first(it: Iterable[_T]) -> _T | None:
    """Get the first element of an arbitrary iterable, or None."""
    return next(iter(it), None)


def first_where(it: Iterable[_T], predicate: Callable[[_T], bool]) -> _T | None:
    """Get the first element of an arbitrary iterable that satisfies the predicate, or None."""
    return first(el for el in it if predicate(el))


class FrozenDict(dict[_K, _V]):
    def __setitem__(self, k: _K, v: _V) -> None:
        raise RuntimeError("immutable")

    def __hash__(self) -> int:  # type: ignore[override]
        return hash(frozenset(self.items()))
