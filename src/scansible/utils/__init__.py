"""Miscellaneous utilities."""

from __future__ import annotations

from typing import TypeVar, cast, override

import itertools
from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence


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


class SourceFileMap[FileType](Mapping[str, FileType]):
    """A collection of source files of a certain type, supporting stem-based indexing.

    This provides a convenient API to find source files without needing to take the concrete
    extension (.yml, .yaml, or .json) into account.

    Can optionally be given a search prefix. When provided, each lookup will attempt to resolve
    a prefixed file name, and fall back to unprefixed search later. This can be useful when all
    files in the map are in the same root directory. For instance, a file map for role task files
    can use "tasks/" as a prefix, allowing individual task files to be accessed without prefixing
    "tasks/" in the lookup.
    """

    def __init__(
        self, file_list: Iterable[tuple[str, FileType]], *, prefix: str = ""
    ) -> None:
        self._mapping: Mapping[str, FileType] = FrozenDict(
            {path: file for path, file in file_list}
        )
        # If prefix is given, prioritise with the prefix but try without the prefix afterwards.
        self._prefixes: Sequence[str] = (prefix, "") if prefix else ("",)

    @override
    def __getitem__(self, key: str) -> FileType:
        for prefix in self._prefixes:
            for ext in (".yml", ".yaml", ".json", ""):
                file_name = f"{prefix}{key}{ext}"
                if file_name in self._mapping:
                    return self._mapping[file_name]

        raise KeyError(f"No file named {key}")

    @override
    def __len__(self) -> int:
        return len(self._mapping)

    @override
    def __iter__(self) -> Iterator[str]:
        return iter(self._mapping)
