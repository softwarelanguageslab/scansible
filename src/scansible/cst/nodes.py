from __future__ import annotations

from typing import TYPE_CHECKING, Self, override

from datetime import date, datetime

from scansible.utils import HasLocation, Location

if TYPE_CHECKING:
    from collections.abc import Iterable


def _get_location(location: Location | None, value: object) -> Location:
    """Return either the location (if defined), the location of the given value, or a synthetic location."""
    if location is not None:
        return location

    if isinstance(value, HasLocation):
        return value.__location__

    return Location.synthetic()


class YamlNode(HasLocation):
    """Base class for YAML nodes."""

    __slots__: tuple[str, ...] = ()
    __location__: Location


## Custom YAML subclasses
class YamlStr(str, YamlNode):
    """String originating from a YAML document, with location information."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __new__(cls, value: str, *, location: Location | None = None) -> Self:
        # ruamel.yaml inserts <BEL> (0x07, \a) characters in multi-line folded strings to indicate
        # where the string was split, so that the split can be reconstructed later. Remove these.
        # TODO: We should probably also keep track of these so we can track source locations during string manipulation.
        obj = str.__new__(cls, value.replace("\a", ""))
        obj.__location__ = _get_location(location, value)
        return obj


class YamlInt(int, YamlNode):
    """Integer originating from a YAML document, with location information."""

    # int subclasses can't use __slots__ for extra attributes (CPython restriction),
    # so this ends up with a __dict__ unlike its siblings.

    def __new__(cls, value: int, *, location: Location | None = None) -> Self:
        obj = int.__new__(cls, value)
        obj.__location__ = _get_location(location, value)
        return obj


class YamlBool(YamlNode):
    """Boolean originating from a YAML document, with location information.

    Note that this is NOT a subclass of `bool`.
    """

    __slots__: tuple[str, ...] = ("__location__", "_real_bool")

    __location__: Location
    _real_bool: bool

    def __init__(
        self,
        value: bool,  # noqa: FBT001
        *,
        location: Location | None = None,
    ) -> None:
        self._real_bool = value
        self.__location__ = _get_location(location, value)

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
    """Float originating from a YAML document, with location information."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __new__(cls, value: float, *, location: Location | None = None) -> Self:
        obj = float.__new__(cls, value)
        obj.__location__ = _get_location(location, value)
        return obj


class YamlDate(date, YamlNode):
    """Date originating from a YAML document, with location information."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __new__(cls, value: date, *, location: Location | None = None) -> Self:
        obj = date.__new__(cls, value.year, value.month, value.day)
        obj.__location__ = _get_location(location, value)
        return obj


class YamlDatetime(datetime, YamlNode):
    """Datetime originating from a YAML document, with location information."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __new__(cls, value: datetime, *, location: Location | None = None) -> Self:
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
        obj.__location__ = _get_location(location, value)
        return obj


class YamlVaultValue(str, YamlNode):
    """Vault-encrypted value originating from a YAML document, with location information."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __new__(cls, value: str, *, location: Location | None = None) -> Self:
        obj = str.__new__(cls, value)
        obj.__location__ = _get_location(location, value)
        return obj


class YamlUnsafeStr(str, YamlNode):
    """Unsafe string originating from a YAML document, with location information.

    Unsafe strings should not be templated."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __new__(cls, value: str, *, location: Location | None = None) -> Self:
        obj = str.__new__(cls, value)
        obj.__location__ = _get_location(location, value)
        return obj


class YamlNone(YamlNode):
    """Null value originating from a YAML document, with location information.

    Note that this is NOT a subclass of `NoneType` (impossible in Python).
    Compare using `==` rather than `is None`.
    """

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __init__(self, *, location: Location | None = None) -> None:
        self.__location__ = location or Location.synthetic()

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
    """Sequence originating from a YAML document, with location information."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __init__(
        self,
        value: Iterable[T] | None = None,
        *,
        location: Location | None = None,
    ) -> None:
        if value is not None:
            super().__init__(value)
        else:
            super().__init__()
        self.__location__ = _get_location(location, value)


class YamlMap[K: YamlScalar, V: YamlValue](dict[K, V], YamlNode):
    """Mapping originating from a YAML document, with location information."""

    __slots__: tuple[str, ...] = ("__location__",)
    __location__: Location

    def __init__(
        self,
        value: Iterable[tuple[K, V]] | None = None,
        *,
        location: Location | None = None,
    ) -> None:
        if value is not None:
            super().__init__(value)
        else:
            super().__init__()
        self.__location__ = _get_location(location, value)

    @override
    def copy(self) -> YamlMap[K, V]:
        return YamlMap(self.items(), location=self.__location__)


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
