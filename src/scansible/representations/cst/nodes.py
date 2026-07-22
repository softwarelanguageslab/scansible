from __future__ import annotations

from typing import NamedTuple, Protocol, override

from collections.abc import Iterable
from datetime import date, datetime

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


class Positioned(Protocol):
    """Mixin for elements with a code position."""

    __position__: Position


class YamlNode:
    """Base class for YAML nodes."""

    pass


## Custom YAML subclasses
class YamlStr(str, YamlNode, Positioned):
    """String originating from a YAML document, with position information."""

    __position__: Position

    def __new__(cls, value: str, position: Position) -> YamlStr:
        obj = str.__new__(cls, value)
        obj.__position__ = position
        return obj


class YamlInt(int, YamlNode, Positioned):
    """Integer originating from a YAML document, with position information."""

    __position__: Position

    def __new__(cls, value: int, position: Position) -> YamlInt:
        obj = int.__new__(cls, value)
        obj.__position__ = position
        return obj


class YamlBool(YamlNode, Positioned):
    """Boolean originating from a YAML document, with position information.

    Note that this is NOT a subclass of `bool`.
    """

    _real_bool: bool

    __position__: Position

    def __init__(self, value: bool, position: Position) -> None:
        self._real_bool = value
        self.__position__ = position

    def __bool__(self) -> bool:
        return self._real_bool

    @override
    def __eq__(self, other: object) -> bool:
        if isinstance(other, YamlBool):
            return self._real_bool == other._real_bool
        return self._real_bool == other

    @override
    def __hash__(self) -> int:
        return hash(self._real_bool)


class YamlFloat(float, YamlNode, Positioned):
    """Float originating from a YAML document, with position information."""

    __position__: Position

    def __new__(cls, value: float, position: Position) -> YamlFloat:
        obj = float.__new__(cls, value)
        obj.__position__ = position
        return obj


class YamlDate(date, YamlNode, Positioned):
    """Date originating from a YAML document, with position information."""

    __position__: Position

    def __new__(cls, value: date, position: Position) -> YamlDate:
        obj = date.__new__(cls, value.year, value.month, value.day)
        obj.__position__ = position
        return obj


class YamlDatetime(datetime, YamlNode, Positioned):
    """Datetime originating from a YAML document, with position information."""

    __position__: Position

    def __new__(cls, value: datetime, position: Position) -> YamlDatetime:
        obj = datetime.__new__(
            cls,
            value.year,
            value.month,
            value.day,
            value.hour,
            value.minute,
            value.second,
            value.microsecond,
            value.tzinfo,
        )
        obj.__position__ = position
        return obj


class YamlVaultValue(str, YamlNode, Positioned):
    """Vault-encrypted value originating from a YAML document, with position information."""

    __position__: Position

    def __new__(cls, value: str, position: Position) -> YamlVaultValue:
        obj = str.__new__(cls, value)
        obj.__position__ = position
        return obj


class YamlUnsafeStr(str, YamlNode, Positioned):
    """Unsafe string originating from a YAML document, with position information.

    Unsafe strings should not be templated."""

    __position__: Position

    def __new__(cls, value: str, position: Position) -> YamlUnsafeStr:
        obj = str.__new__(cls, value)
        obj.__position__ = position
        return obj


class YamlNone(YamlNode, Positioned):
    """Null value originating from a YAML document, with position information.

    Note that this is NOT a subclass of `NoneType` (impossible in Python).
    Compare using `==` rather than `is None`.
    """

    __position__: Position

    def __init__(self, position: Position) -> None:
        self.__position__ = position

    def __bool__(self) -> bool:
        return False

    @override
    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, YamlNone)

    @override
    def __hash__(self) -> int:
        return hash(None)


class YamlSeq[T: YamlValue](list[T], YamlNode, Positioned):
    """Sequence originating from a YAML document, with position information."""

    __position__: Position

    def __init__(self, value: Iterable[T] | None = None, *, position: Position) -> None:
        if value is not None:
            super().__init__(value)
        else:
            super().__init__()
        self.__position__ = position


class YamlMap[K: YamlScalar, V: YamlValue](dict[K, V], YamlNode, Positioned):
    """Mapping originating from a YAML document, with position information."""

    __position__: Position

    def __init__(
        self, value: Iterable[tuple[K, V]] | None = None, *, position: Position
    ) -> None:
        if value is not None:
            super().__init__(value)
        else:
            super().__init__()
        self.__position__ = position


#: Type union of scalar values originating from YAML documents.
type YamlScalar = (
    YamlStr
    | YamlInt
    | YamlBool
    | YamlFloat
    | YamlDate
    | YamlDatetime
    | YamlVaultValue
    | YamlUnsafeStr
    | YamlNone
)
#: Type union of composite values originating from YAML documents.
type YamlComposite = YamlSeq[YamlValue] | YamlMap[YamlScalar, YamlValue]
#: Type union of values originating from YAML documents.
type YamlValue = YamlScalar | YamlComposite
