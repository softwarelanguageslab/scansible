"""Miscellaneous utilities."""

from __future__ import annotations

from typing import TypeVar, cast

import itertools
from collections.abc import Callable, Iterable, Mapping, Sequence


class Sentinel:
    def __repr__(self) -> str:
        return "SENTINEL"


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


def make_immutable(obj: _T) -> _T:
    if isinstance(obj, str):
        return obj  # type: ignore[return-value]
    if isinstance(obj, Mapping):
        return FrozenDict(
            {make_immutable(k): make_immutable(v) for k, v in obj.items()}
        )  # type: ignore
    if isinstance(obj, Sequence):
        return tuple([make_immutable(e) for e in obj])  # type: ignore

    return obj


def join_sequences(seq1: Sequence[_T], seq2: Sequence[_T]) -> Sequence[_T]:
    return tuple(itertools.chain(seq1, seq2))


def ensure_sequence(obj: _T | Sequence[_T] | None) -> Sequence[_T]:
    if obj is None:
        return []
    if isinstance(obj, Sequence):
        return cast(Sequence[_T], obj)
    return [obj]
