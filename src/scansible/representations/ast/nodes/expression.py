"""AST nodes representing expressions used in Ansible content.

Expressions can be literal values and Jinja2 expressions, either bare (without `{{ }}`) or wrapped (with `{{ }}`).

`Expression` and `Condition` are `ASTNode` instances that eagerly parse their source string into a
Jinja2 AST (`template`) at validation time, alongside the original source (`raw`).

Literals are deliberately kept separate from the CST nodes to enforce the distinction between the CST and the AST.
Moreover, AST nodes may perform type coercions that the CST nodes do not, and are used in different ways.
"""

from __future__ import annotations

from typing import Annotated, Any, Callable, Final, Protocol, Self, get_args, override

import decimal
import keyword
from abc import abstractmethod
from collections.abc import Iterable, Mapping, Sequence
from datetime import date, datetime

from jinja2 import Environment, TemplateSyntaxError
from jinja2 import nodes as j2_nodes
from pydantic import (
    BeforeValidator,
    Discriminator,
    GetCoreSchemaHandler,
    Tag,
    TypeAdapter,
    ValidationError,
    model_validator,
)
from pydantic_core import core_schema

from scansible.representations.cst import YamlUnsafeStr, YamlVaultValue
from scansible.utils import FrozenDict, Position, Positioned

from ..common import BrokenTask, ExtractionContext
from .base import ASTNode

_JINJA_ENV = Environment(cache_size=0)

#: Placeholder position used as the default for directly constructed nodes.
_SYNTHETIC_POSITION: Final = Position.synthetic()


def _get_position(value: object) -> Position:
    if isinstance(value, Positioned):
        return value.__position__
    return Position.synthetic()


def _is_literal(raw: str, template: j2_nodes.Template) -> bool:
    return not raw or (
        len(template.body) == 1
        and isinstance(output := template.body[0], j2_nodes.Output)
        and len(output.nodes) == 1
        and isinstance((data := output.nodes[0]), j2_nodes.TemplateData)
        # Check that parsing didn't remove comments etc.
        and data.data.strip() == raw.strip()
    )


class Expression(ASTNode, frozen=True, arbitrary_types_allowed=True):
    """AST node representing a Jinja2 expression."""

    raw: StrLiteral
    template: j2_nodes.Template

    @classmethod
    def _parse_expression(cls, value: str) -> j2_nodes.Template:
        """Parse an expression to a template, and raise ValueError in case of malformed expressions."""
        # Quickly check whether any Jinja2 delimiters are present
        delimiters = (
            _JINJA_ENV.block_start_string,
            _JINJA_ENV.variable_start_string,
            _JINJA_ENV.comment_start_string,
        )
        if not any(delimiter in value for delimiter in delimiters):
            raise ValueError("Jinja2 expressions must contain Jinja2 delimiters")

        try:
            template = _JINJA_ENV.parse(value)
        except TemplateSyntaxError as tse:
            raise ValueError(f"Template Syntax Error: {tse}") from tse

        if _is_literal(value, template):
            raise ValueError("Expression must contain Jinja2 constructs")

        return template

    @model_validator(mode="before")
    @classmethod
    def _parse_from_string(cls, data: object) -> object:
        """Validate and parse an expression string, and return a format suitable for Pydantic to ingest."""
        if not isinstance(data, str):
            raise ValueError("expressions must be strings")
        if isinstance(data, YamlUnsafeStr):
            raise ValueError("refusing to treat an unsafe string as an expression")

        return {
            "raw": data,
            "template": cls._parse_expression(data),
            "__position__": _get_position(data),
        }


class Condition(Expression, frozen=True):
    """AST node representing an Ansible condition.

    Ansible conditions are special-case expressions without surrounding braces. We model
    them as subtypes of expressions with specialised handling so that consumers can use
    the standard Expression interface without concerning themselves about bare conditions.
    """

    @classmethod
    @override
    def _parse_expression(cls, value: str) -> j2_nodes.Template:
        """Parse an condition to a template, and raise ValueError in case of malformed conditions.

        Conditions are wrapped by Ansible in another Jinja2 expression and thus should not contain braces.
        We consider an expression that contains Jinja2 braces to be an error. Note that some Ansible versions
        allow this, we conservatively do not.
        """
        # Note that we cannot use the quick check for delimiters as done in `Expression`, as that overapproximates
        # and thus cannot guarantee that a string is NOT an expression. Therefore, we'll parse the expression as is,
        # reject any non-literals, and parse it wrapped.

        try:
            template = _JINJA_ENV.parse(value)
            if not _is_literal(value, template):
                raise ValueError("Conditions must not contain any Jinja2 brace syntax")
        except TemplateSyntaxError:
            # ignore for now, it might parse correctly when wrapped.
            pass

        wrapped = "{% if " + value + " %} True {% else %} False {% endif %}"
        try:
            template = _JINJA_ENV.parse(wrapped)
        except TemplateSyntaxError as tse:
            raise ValueError(f"Template Syntax Error: {tse}") from tse

        assert isinstance(template.body[0], j2_nodes.If)
        return j2_nodes.Template([template.body[0].test])


class Identifier(str, Positioned):
    """AST node representing an identifier, e.g., a variable name."""

    __position__: Position

    def __new__(cls, value: str, *, position: Position = _SYNTHETIC_POSITION) -> Self:
        obj = str.__new__(cls, value)
        obj.__position__ = position
        return obj

    @classmethod
    def __get_pydantic_core_schema__(
        cls, source_type: object, handler: GetCoreSchemaHandler
    ) -> core_schema.CoreSchema:
        def validate(value: object) -> Self:
            if not isinstance(value, str):
                raise ValueError(f"Identifiers must be strings, got {type(value)}")
            if not (value.isascii() and value.isidentifier()):
                raise ValueError(f"Expected a valid identifier, got {value}")
            if keyword.iskeyword(value):
                raise ValueError(f"{value} is a reserved keyword")

            return cls(value, position=_get_position(value))

        return core_schema.no_info_after_validator_function(
            validate, core_schema.any_schema()
        )

    @classmethod
    def from_object(cls, o: object) -> Self:
        """Create an identifier from an arbitrary object."""
        return TypeAdapter(cls).validate_python(o)


class Literal(Positioned, Protocol):
    """AST node representing a literal value."""

    __position__: Position

    @classmethod
    @abstractmethod
    def _validate(cls, value: object) -> object:
        """Validate the given value and coerce it to a value used to construct an instance of this literal."""
        ...

    @classmethod
    def _construct(
        cls,
        original_value: Any,  # pyright: ignore[reportExplicitAny, reportAny]
        coerced_value: Any,  # pyright: ignore[reportExplicitAny, reportAny]
        position: Position,
    ) -> Self:
        """Construct an instance of the class, given the original and coerced value and its position."""
        return cls(coerced_value, position=position)  # pyright: ignore[reportCallIssue]

    @classmethod
    def _construct_and_wrap(cls, original_value: object, coerced_value: object) -> Self:
        """Construct an instance, deriving its position from the original value.

        Unlikely to need overriding, instead, override `_construct`.
        """
        return cls._construct(
            original_value, coerced_value, _get_position(original_value)
        )

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

    def __new__(cls, value: str, *, position: Position = _SYNTHETIC_POSITION) -> Self:
        obj = str.__new__(cls, value)
        obj.__position__ = position
        return obj

    @classmethod
    @override
    def _construct(
        cls, original_value: object, coerced_value: str, position: Position
    ) -> Self:
        obj = cls(coerced_value, position=position)
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

    def __new__(cls, value: int, *, position: Position = _SYNTHETIC_POSITION) -> Self:
        obj = int.__new__(cls, value)
        obj.__position__ = position
        return obj

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

    def __new__(cls, value: float, *, position: Position = _SYNTHETIC_POSITION) -> Self:
        obj = float.__new__(cls, value)
        obj.__position__ = position
        return obj

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

    def __new__(cls, value: float, *, position: Position = _SYNTHETIC_POSITION) -> Self:
        obj = float.__new__(cls, value)
        obj.__position__ = position
        return obj

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

    def __init__(
        self, value: bool, *, position: Position = _SYNTHETIC_POSITION
    ) -> None:
        self._real_bool = value
        self.__position__ = position

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

        if isinstance(value, str):
            value = value.lower().strip()

        if value in ("y", "yes", "on", "1", "true", "t", 1, 1.0):
            return True
        elif value in ("n", "no", "off", "0", "false", "f", 0, 0.0):
            return False

        raise ValueError("Value cannot be coerced to a boolean")


class DateLiteral(date, Literal):
    """AST node representing a literal date."""

    __position__: Position

    def __new__(cls, value: date, *, position: Position = _SYNTHETIC_POSITION) -> Self:
        obj = date.__new__(cls, value.year, value.month, value.day)
        obj.__position__ = position
        return obj

    @classmethod
    @override
    def _validate(cls, value: object) -> date:
        """Coerce the given value to a date."""
        if not isinstance(value, date):
            raise ValueError("Expected date")
        return value


class DatetimeLiteral(datetime, Literal):
    """AST node representing a literal datetime."""

    __position__: Position

    def __new__(
        cls, value: datetime, *, position: Position = _SYNTHETIC_POSITION
    ) -> Self:
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

    @classmethod
    @override
    def _validate(cls, value: object) -> datetime:
        """Coerce the given value to a datetime."""
        if not isinstance(value, datetime):
            raise ValueError("Expected datetime")
        return value


class SeqLiteral[T](tuple[T, ...], Literal):
    """AST node representing a literal sequence."""

    __position__: Position

    def __new__(
        cls, value: Iterable[T] = (), *, position: Position = _SYNTHETIC_POSITION
    ) -> Self:
        obj = tuple.__new__(cls, value)  # pyright: ignore[reportUnknownMemberType]
        obj.__position__ = position
        return obj

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


class LenientSeqLiteral[T](SeqLiteral[T]):
    """Sequence literal that drops invalid items in lenient mode, instead of failing the whole sequence.

    Unlike `SeqLiteral`, a bare non-sequence value is never coerced into a one-item sequence:
    none of the fields using this type accept a lone item as shorthand for a one-item list.
    """

    @classmethod
    @override
    def _validate(cls, value: object) -> Sequence[object]:
        if value == None:  # noqa: E711 -- could be YamlNone
            return ()
        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            raise ValueError("Expected a sequence")
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
            value: object,
            inner: core_schema.ValidatorFunctionWrapHandler,
            info: core_schema.ValidationInfo,
        ) -> Self:
            coerced = cls._validate(value)
            context = info.context

            if context is not None and not isinstance(context, ExtractionContext):
                raise ValueError("Expected context to be an ExtractionContext")

            if context is None or not context.lenient:
                validated_items = inner(list(coerced))  # pyright: ignore[reportAny]
                return cls._construct_and_wrap(value, tuple(validated_items))  # pyright: ignore[reportAny]

            results: list[object] = []
            for raw in coerced:
                try:
                    (validated,) = inner([raw])  # pyright: ignore[reportAny]
                except ValidationError as exc:
                    context.broken_tasks.append(BrokenTask(raw=raw, reason=exc))
                else:
                    results.append(validated)  # pyright: ignore[reportAny]

            return cls._construct_and_wrap(value, tuple(results))

        return core_schema.with_info_wrap_validator_function(validate, list_schema)


class MapLiteral[K, V](FrozenDict[K, V], Literal):
    """AST node representing a literal mapping."""

    __position__: Position

    def __init__(
        self,
        value: Mapping[K, V] | Iterable[tuple[K, V]] | None = None,
        *,
        position: Position = _SYNTHETIC_POSITION,
    ) -> None:
        if value is not None:
            super().__init__(value)
        else:
            super().__init__()
        self.__position__ = position

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


__all__ = [
    "Expression",
    "Condition",
    "Identifier",
    "Literal",
    "StrLiteral",
    "IntLiteral",
    "FloatLiteral",
    "PercentLiteral",
    "BoolLiteral",
    "DateLiteral",
    "DatetimeLiteral",
    "SeqLiteral",
    "LenientSeqLiteral",
    "MapLiteral",
    "ScalarLiteral",
    "CompositeLiteral",
    "AnyLiteral",
    "AnyExpression",
]
