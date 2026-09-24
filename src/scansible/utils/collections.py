"""Utilities related to collections."""

from __future__ import annotations

from typing import cast, override

import itertools
from collections.abc import Callable, Iterable, Sequence


def first[T](it: Iterable[T]) -> T | None:
    """Get the first element of an arbitrary iterable, or None."""
    return next(iter(it), None)


def first_where[T](it: Iterable[T], predicate: Callable[[T], bool]) -> T | None:
    """Get the first element of an arbitrary iterable that satisfies the predicate, or None."""
    return first(el for el in it if predicate(el))


class FrozenDict[K, V](dict[K, V]):
    __slots__: tuple[str, ...] = ()

    @override
    def __setitem__(self, k: K, v: V) -> None:
        raise RuntimeError("immutable")

    @override
    def __hash__(self) -> int:  # pyright: ignore[reportIncompatibleVariableOverride]
        return hash(frozenset(self.items()))


def join_sequences[T](seq1: Sequence[T], seq2: Sequence[T]) -> Sequence[T]:
    return tuple(itertools.chain(seq1, seq2))


def ensure_sequence[T](obj: T | Sequence[T] | None) -> Sequence[T]:
    if obj is None:
        return []
    if isinstance(obj, Sequence):
        return cast(Sequence[T], obj)
    return [obj]
