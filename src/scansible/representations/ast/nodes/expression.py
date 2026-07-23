"""AST nodes representing expressions used in Ansible content.

Expressions can be literal values and Jinja2 expressions, either bare (without `{{ }}`) or wrapped (with `{{ }}`).

For now, expression nodes are validated subclasses of plain `str` and can be used just like an actual `str`.
In the future, they may become full-fledged `ASTNode` instances with parsed expressions.

Literals are deliberately kept separate from the CST nodes to enforce the distinction between the CST and the AST.
Moreover, AST nodes may perform type coercions that the CST nodes do not, and are used in different ways.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Final, Protocol, Self, get_args, override

import decimal
import keyword
from abc import abstractmethod
from collections.abc import Mapping, Sequence
from datetime import date, datetime

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar
from pydantic import BeforeValidator, Discriminator, GetCoreSchemaHandler, Tag
from pydantic_core import core_schema

from scansible.representations.cst import YamlNode, YamlUnsafeStr, YamlVaultValue
from scansible.utils import FrozenDict, Position, Positioned


def _is_template(expr: str) -> bool:
    templar = Templar(DataLoader())
    return templar.is_template(expr)


def _get_position(value: object) -> Position:
    if isinstance(value, YamlNode):
        return value.__position__
    return Position.synthetic()


class Expression(str, Positioned):
    """AST node representing a Jinja2 expression."""

    __position__: Position

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate(value: object) -> Self:
            if not isinstance(value, str):
                raise ValueError("expressions must be strings")
            if not _is_template(value):
                raise ValueError("not a valid expression")
            if isinstance(value, YamlUnsafeStr):
                raise ValueError("expression is marked unsafe")

            object = cls(value)
            object.__position__ = _get_position(value)
            return object

        return core_schema.no_info_after_validator_function(
            validate, core_schema.any_schema()
        )


class Condition(str, Positioned):
    """AST node representing an Ansible condition.

    Ansible conditions are Jinja2 expressions without surrounding braces.
    """

    __position__: Position

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate(value: str) -> Self:
            # FIXME: We need validation here to make sure it's a correct condition, but
            # the validation is complex and currently lives in the PDG builder.
            # When doing such validation, we may as well parse the expressions/conditions too.
            object = cls(value)
            object.__position__ = _get_position(value)
            return object

        return core_schema.no_info_after_validator_function(
            validate, core_schema.str_schema()
        )


class Identifier(str, Positioned):
    """AST node representing an identifier, e.g., a variable name."""

    __position__: Position

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate(value: str) -> Self:
            if not (value.isascii() and value.isidentifier()):
                raise ValueError(f"Expected a valid identifier, got {value}")
            if keyword.iskeyword(value):
                raise ValueError(f"{value} is a reserved keyword")

            object = cls(value)
            object.__position__ = _get_position(value)
            return object

        return core_schema.no_info_after_validator_function(
            validate, core_schema.str_schema()
        )


class Literal(Positioned, Protocol):
    """AST node representing a literal value."""

    __position__: Position

    @classmethod
    @abstractmethod
    def _validate(cls, value: object) -> object:
        """Validate the given value and coerce it to a value used to construct an instance of this literal."""
        ...

    @classmethod
    def _construct(cls, original_value: Any, coerced_value: Any) -> Self:  # pyright: ignore[reportExplicitAny, reportAny]
        """Construct an instance of the class, given the original and coerced value."""
        return cls(coerced_value)  # pyright: ignore[reportCallIssue]

    @classmethod
    def _construct_and_wrap(cls, original_value: object, coerced_value: object) -> Self:
        """Construct an instance and set the position.

        Unlikely to need overriding, instead, override `_construct`.
        """
        wrapped = cls._construct(original_value, coerced_value)
        wrapped.__position__ = _get_position(original_value)
        return wrapped

    @classmethod
    def _make_validator(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> Callable[[object], Self]:
        """Create the Pydantic validator for this class.

        Must call `cls._validate` and `cls._construct_and_wrap`.
        """

        def validator(value: object) -> Self:
            validated_value = cls._validate(value)
            wrapped = cls._construct_and_wrap(value, validated_value)
            return wrapped

        return validator

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        return core_schema.no_info_after_validator_function(
            cls._make_validator(source_type, handler), core_schema.any_schema()
        )


class StrLiteral(str, Literal):
    """AST node representing a literal string.

    This includes unsafe string and vault-encrypted values.
    For vault-encrypted values, we don't know what the underlying value could be coerced to, so we'll
    approximate it as a string.
    """

    __position__: Position
    #: Whether this string is in fact a vault-encrypted value.
    is_vaulted: Final[bool] = False

    @classmethod
    @override
    def _construct(cls, original_value: object, coerced_value: str) -> Self:
        obj = cls(coerced_value)
        obj.is_vaulted = isinstance(original_value, YamlVaultValue)  # pyright: ignore[reportAttributeAccessIssue]
        return obj

    @classmethod
    @override
    def _validate(cls, value: object) -> str:
        """Coerce the given value to a string, like Ansible does."""
        if isinstance(value, str):
            return value
        if isinstance(value, bytes):
            return value.decode()
        try:
            return str(value)
        except UnicodeError:
            return repr(value)


class IntLiteral(int, Literal):
    """AST node representing a literal integer."""

    __position__: Position

    @classmethod
    @override
    def _validate(cls, value: object) -> int:
        """Coerce the given value to an int, like Ansible does."""
        if isinstance(value, int):
            return value

        try:
            decimal_value = decimal.Decimal(value)  # pyright: ignore[reportArgumentType]
            int_value = int(decimal_value)
        except (decimal.DecimalException, TypeError) as e:
            raise ValueError from e

        if int_value != decimal_value:
            raise ValueError(f"Floating-point value {value!r} would be truncated.")
        return int_value


class FloatLiteral(float, Literal):
    """AST node representing a literal float."""

    __position__: Position

    @classmethod
    @override
    def _validate(cls, value: object) -> float:
        """Coerce the given value to a float, like Ansible does."""
        try:
            return float(value)  # pyright: ignore[reportArgumentType]
        except TypeError as e:
            raise ValueError from e


class PercentLiteral(float, Literal):
    """AST node representing a literal percentage."""

    __position__: Position

    @classmethod
    @override
    def _validate(cls, value: object) -> float:
        """Coerce the given value to a percent (float), like Ansible does."""
        if isinstance(value, str):
            value = value.replace("%", "")
        try:
            return float(value)  # pyright: ignore[reportArgumentType]
        except TypeError as e:
            raise ValueError from e


class BoolLiteral(Literal):
    """AST node representing a literal boolean.

    Note that this is NOT a subclass of `bool`.
    """

    _real_bool: bool
    __position__: Position

    def __init__(self, value: bool) -> None:
        self._real_bool = value

    def __bool__(self) -> bool:
        return self._real_bool

    @override
    def __str__(self) -> str:
        return str(self._real_bool)

    @override
    def __eq__(self, other: object) -> bool:
        if isinstance(other, BoolLiteral):
            return self._real_bool == other._real_bool
        return self._real_bool == other

    @override
    def __hash__(self) -> int:
        return hash(self._real_bool)

    @classmethod
    @override
    def _validate(cls, value: object) -> bool:
        """Coerce the given value to a boolean, like Ansible does."""
        if isinstance(value, bool):
            return value

        if value in ("y", "yes", "on", "1", "true", "t", 1, 1.0):
            return True
        elif value in ("n", "no", "off", "0", "false", "f", 0, 0.0):
            return False

        raise ValueError("Value cannot be coerced to a boolean")


class DateLiteral(date, Literal):
    """AST node representing a literal date."""

    __position__: Position

    @classmethod
    @override
    def _validate(cls, value: object) -> date:
        """Coerce the given value to a date."""
        if not isinstance(value, date):
            raise ValueError("Expected date")
        return value

    @classmethod
    @override
    def _construct(cls, original_value: object, coerced_value: date) -> Self:
        return cls(coerced_value.year, coerced_value.month, coerced_value.day)


class DatetimeLiteral(datetime, Literal):
    """AST node representing a literal datetime."""

    __position__: Position

    @classmethod
    @override
    def _validate(cls, value: object) -> datetime:
        """Coerce the given value to a datetime."""
        if not isinstance(value, datetime):
            raise ValueError("Expected datetime")
        return value

    @classmethod
    @override
    def _construct(cls, original_value: object, coerced_value: datetime) -> Self:
        return cls(
            coerced_value.year,
            coerced_value.month,
            coerced_value.day,
            coerced_value.hour,
            coerced_value.minute,
            coerced_value.second,
            coerced_value.microsecond,
            coerced_value.tzinfo,
        )


class SeqLiteral[T](tuple[T, ...], Literal):
    """AST node representing a literal sequence."""

    __position__: Position

    @classmethod
    @override
    def _validate(cls, value: object) -> Sequence[object]:
        """Coerce the given value to a sequence, like Ansible does."""
        if value == None:  # noqa: E711  # Could be YamlNone
            return ()
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            value = (value,)
        return value

    @classmethod
    @override
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        (item_type,) = get_args(source_type)  # pyright: ignore[reportAny]
        item_schema = handler.generate_schema(item_type)
        list_schema = core_schema.list_schema(item_schema)

        def validate(
            value: object, inner: core_schema.ValidatorFunctionWrapHandler
        ) -> Self:
            coerced = cls._validate(value)
            validated_items = inner(list(coerced))  # pyright: ignore[reportAny]
            return cls._construct_and_wrap(value, tuple(validated_items))  # pyright: ignore[reportAny]

        return core_schema.no_info_wrap_validator_function(validate, list_schema)


class MapLiteral[K, V](FrozenDict[K, V], Literal):
    """AST node representing a literal mapping."""

    __position__: Position

    @classmethod
    @override
    def _validate(cls, value: object) -> Mapping[object, object]:
        """Coerce the given value to a mapping, like Ansible does."""
        if value == None:  # noqa: E711
            return {}
        if not isinstance(value, Mapping):
            raise ValueError("Cannot coerce value to mapping")
        return value  # pyright: ignore[reportUnknownVariableType]

    @classmethod
    @override
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        key_type, value_type = get_args(source_type)  # pyright: ignore[reportAny]
        key_schema = handler.generate_schema(key_type)
        value_schema = handler.generate_schema(value_type)
        map_schema = core_schema.dict_schema(key_schema, value_schema)

        def validate(
            value: object, inner: core_schema.ValidatorFunctionWrapHandler
        ) -> Self:
            coerced = cls._validate(value)
            validated_items = inner(dict(coerced))  # pyright: ignore[reportAny]
            return cls._construct_and_wrap(value, validated_items)  # pyright: ignore[reportAny]

        return core_schema.no_info_wrap_validator_function(validate, map_schema)


def _get_literal_type_tag(obj: object) -> str:
    # Special case composite types as there may be several concrete types.
    if isinstance(obj, Mapping):
        return "map"
    elif isinstance(obj, Sequence) and not isinstance(obj, (str, bytes)):
        return "seq"

    # For scalars, use the input type name as the discriminator, also for CST nodes.
    tag = type(obj).__name__.removeprefix("Yaml").lower()
    # Route vault values and unsafe values to str.
    if tag in ("vaultvalue", "unsafestr"):
        tag = "str"
    return tag


#: Discriminated type union of scalar literal values, dispatched based on input value type.
#: This dispatching enables Pydantic to choose the best-matching literal type based on the input
#: value's type.
type ScalarLiteral = Annotated[
    (
        Annotated[StrLiteral, Tag("str")]
        | Annotated[IntLiteral, Tag("int")]
        | Annotated[BoolLiteral, Tag("bool")]
        | Annotated[FloatLiteral, Tag("float")]
        | Annotated[DateLiteral, Tag("date")]
        | Annotated[DatetimeLiteral, Tag("datetime")]
        # Transform YamlNone into None for simplicity.
        | Annotated[None, BeforeValidator(lambda _: None), Tag("none")]  # pyright: ignore[reportAny]
    ),
    Discriminator(_get_literal_type_tag),
]
#: Discriminated type union of composite literal values, dispatched based on input value type.
type CompositeLiteral = Annotated[
    (
        Annotated[SeqLiteral[AnyExpression], Tag("seq")]
        | Annotated[MapLiteral[ScalarLiteral, AnyExpression], Tag("map")]
    ),
    Discriminator(_get_literal_type_tag),
]
#: Discriminated type union of literal values.
type AnyLiteral = ScalarLiteral | CompositeLiteral
#: Type union of all expressions.
type AnyExpression = Expression | AnyLiteral
