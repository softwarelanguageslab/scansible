"""Utilities for source code location tracking."""

from __future__ import annotations

from typing import NamedTuple, Protocol, Self, override, runtime_checkable

from dataclasses import dataclass

from ruamel.yaml import StreamMark


class LineColumn(NamedTuple):
    """Pair of line and column numbers."""

    #: Line number, 1-indexed.
    line: int
    #: Column number, 1-indexed.
    column: int

    @classmethod
    def from_yaml_mark(cls, mark: StreamMark) -> LineColumn:
        return cls(line=mark.line + 1, column=mark.column + 1)


@dataclass(frozen=True, slots=True)
class Location:
    """Source code location of an entity."""

    #: Relative path to the file in which this entity occurs.
    path: str
    #: Start position.
    start: LineColumn
    #: End position.
    end: LineColumn

    @classmethod
    def synthetic(cls) -> Self:
        return cls("<unknown>", LineColumn(-1, -1), LineColumn(-1, -1))

    @property
    def is_synthetic(self) -> bool:
        """Whether the location is a placeholder, i.e. not derived from an actual source location."""
        return self.path == "<unknown>"

    @override
    def __str__(self) -> str:
        return f"{self.path}:{self.start.line}:{self.start.column}"


@runtime_checkable
class HasLocation(Protocol):
    """Mixin for elements with a code location."""

    __location__: Location
