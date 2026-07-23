"""Utilities for source code position tracking."""

from __future__ import annotations

from typing import NamedTuple, Protocol

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


class Position(NamedTuple):
    """Source code position of an entity."""

    #: Relative path to the file in which this entity occurs.
    path: str
    #: Start position.
    start: LineColumn
    #: End position.
    end: LineColumn

    @classmethod
    def synthetic(cls) -> Position:
        return cls("<unknown>", LineColumn(-1, -1), LineColumn(-1, -1))

    @property
    def is_synthetic(self) -> bool:
        """Whether the position is a placeholder, i.e. not derived from an actual source location."""
        return self.path == "<unknown>"


class Positioned(Protocol):
    """Mixin for elements with a code position."""

    __position__: Position
