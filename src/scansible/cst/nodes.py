from __future__ import annotations

from typing import Self, override

from collections.abc import Iterable
from datetime import date, datetime

from scansible.utils import Position, Positioned


def _get_position(position: Position | None, value: object) -> Position:
    """Return either the position (if defined), the position of the given value, or a synthetic position."""
    if position is not None:
        return position

    if isinstance(value, Positioned):
        return value.__position__

    return Position.synthetic()


class YamlNode(Positioned):
    """Base class for YAML nodes."""

    __position__: Position


## Custom YAML subclasses
class YamlStr(str, YamlNode):
    """String originating from a YAML document, with position information."""

    def __new__(cls, value: str, *, position: Position | None = None) -> Self:
        # ruamel.yaml inserts <BEL> (0x07, \a) characters in multi-line folded strings to indicate
        # where the string was split, so that the split can be reconstructed later. Remove these.
        # TODO: We should probably also keep track of these so we can track source positions during string manipulation.
        obj = str.__new__(cls, value.replace("\a", ""))
        obj.__position__ = _get_position(position, value)
        return obj


class YamlInt(int, YamlNode):
    """Integer originating from a YAML document, with position information."""

    def __new__(cls, value: int, *, position: Position | None = None) -> Self:
        obj = int.__new__(cls, value)
        obj.__position__ = _get_position(position, value)
        return obj


class YamlBool(YamlNode):
    """Boolean originating from a YAML document, with position information.

    Note that this is NOT a subclass of `bool`.
    """

    _real_bool: bool

    __position__: Position

    def __init__(
        self,
        value: bool,  # noqa: FBT001
        *,
        position: Position | None = None,
    ) -> None:
        self._real_bool = value
        self.__position__ = _get_position(position, value)

    def __bool__(self) -> bool:
        return self._real_bool

    @override
    def __str__(self) -> str:
        return str(self._real_bool)

    @override
    def __eq__(self, other: object) -> bool:
        if isinstance(other, YamlBool):
            return self._real_bool == other._real_bool
        return self._real_bool == other

    @override
    def __hash__(self) -> int:
        return hash(self._real_bool)


class YamlFloat(float, YamlNode):
    """Float originating from a YAML document, with position information."""

    def __new__(cls, value: float, *, position: Position | None = None) -> Self:
        obj = float.__new__(cls, value)
        obj.__position__ = _get_position(position, value)
        return obj


class YamlDate(date, YamlNode):
    """Date originating from a YAML document, with position information."""

    def __new__(cls, value: date, *, position: Position | None = None) -> Self:
        obj = date.__new__(cls, value.year, value.month, value.day)
        obj.__position__ = _get_position(position, value)
        return obj


class YamlDatetime(datetime, YamlNode):
    """Datetime originating from a YAML document, with position information."""

    def __new__(cls, value: datetime, *, position: Position | None = None) -> Self:
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
        obj.__position__ = _get_position(position, value)
        return obj


class YamlVaultValue(str, YamlNode):
    """Vault-encrypted value originating from a YAML document, with position information."""

    def __new__(cls, value: str, *, position: Position | None = None) -> Self:
        obj = str.__new__(cls, value)
        obj.__position__ = _get_position(position, value)
        return obj


class YamlUnsafeStr(str, YamlNode):
    """Unsafe string originating from a YAML document, with position information.

    Unsafe strings should not be templated."""

    def __new__(cls, value: str, *, position: Position | None = None) -> Self:
        obj = str.__new__(cls, value)
        obj.__position__ = _get_position(position, value)
        return obj


class YamlNone(YamlNode):
    """Null value originating from a YAML document, with position information.

    Note that this is NOT a subclass of `NoneType` (impossible in Python).
    Compare using `==` rather than `is None`.
    """

    __position__: Position

    def __init__(self, *, position: Position | None = None) -> None:
        self.__position__ = position or Position.synthetic()

    def __bool__(self) -> bool:
        return False

    @override
    def __str__(self) -> str:
        return "None"

    @override
    def __eq__(self, other: object) -> bool:
        return other is None or isinstance(other, YamlNone)

    @override
    def __hash__(self) -> int:
        return hash(None)


class YamlSeq[T: YamlValue](list[T], YamlNode):
    """Sequence originating from a YAML document, with position information."""

    __position__: Position

    def __init__(
        self,
        value: Iterable[T] | None = None,
        *,
        position: Position | None = None,
    ) -> None:
        if value is not None:
            super().__init__(value)
        else:
            super().__init__()
        self.__position__ = _get_position(position, value)


class YamlMap[K: YamlScalar, V: YamlValue](dict[K, V], YamlNode):
    """Mapping originating from a YAML document, with position information."""

    __position__: Position

    def __init__(
        self,
        value: Iterable[tuple[K, V]] | None = None,
        *,
        position: Position | None = None,
    ) -> None:
        if value is not None:
            super().__init__(value)
        else:
            super().__init__()
        self.__position__ = _get_position(position, value)

    @override
    def copy(self) -> YamlMap[K, V]:
        return YamlMap(self.items(), position=self.__position__)


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
