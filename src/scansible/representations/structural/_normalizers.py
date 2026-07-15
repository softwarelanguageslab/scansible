from __future__ import annotations

from typing import TYPE_CHECKING, get_args, get_origin, override

from abc import ABC, abstractmethod
from collections.abc import Sequence

from pydantic import TypeAdapter, ValidationError, ValidationInfo
from pydantic.fields import FieldInfo

from .common import BrokenTask, ExtractionContext

if TYPE_CHECKING:
    from .nodes.base import ASTEntity


class Normalizer(ABC):
    """Normalization logic for AST models."""

    @classmethod
    @abstractmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        """Perform the normalization."""
        raise NotImplementedError


class NormalizeNone(Normalizer):
    """Normalizer that normalizes `None` values to the field's default."""

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if value is not None:
            return value

        return field_info.get_default(call_default_factory=True, validated_data=value)  # pyright: ignore[reportAny]


class Listify(Normalizer):
    """Normalizer that normalizes single values to a list of that value."""

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if isinstance(value, Sequence) and not isinstance(value, str):
            return value

        return [value]


class Stringify(Normalizer):
    """Normalizer that normalizes non-string values to stringified values.

    By default, it only normalizes int, float, and bool values, and recursively normalizes
    entries in lists.
    """

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if isinstance(value, str):
            return value

        if isinstance(value, (int, float, bool)):
            return str(value)

        if isinstance(value, Sequence):
            return type(value)(
                (
                    cls.normalize(element, field_info, validation_info)
                    for element in value
                )  # pyright: ignore[reportCallIssue]
            )

        return value


class Lenient(Normalizer):
    """Normalizer that enables parsing in sequences to be lenient.

    If the lenient flag is set in the validation context, this normalizer will catch
    any item-specific validation errors and ignore it, omitting that item from the
    resulting list. In non-lenient (strict) mode, the validator acts normally.
    """

    @classmethod
    def _get_contained_type(cls, field_info: FieldInfo) -> type[object]:
        annotation = field_info.annotation

        if (
            annotation is None
            or (origin := get_origin(annotation)) is None
            or not issubclass(origin, Sequence)
        ):
            raise ValueError("Can only mark Sequences as Lenient")

        return get_args(annotation)[0]  # pyright: ignore[reportAny]

    @override
    @classmethod
    def normalize(
        cls, value: object, field_info: FieldInfo, validation_info: ValidationInfo
    ) -> object:
        if not isinstance(value, Sequence):
            return value

        if validation_info.context is None:
            return value

        if not isinstance(validation_info.context, ExtractionContext):  # pyright: ignore[reportAny]
            raise ValueError("Expected context to be an ExtractionContext")

        context = validation_info.context
        if not context.lenient:
            return value

        contained_type = cls._get_contained_type(field_info)
        adapter = TypeAdapter["ASTEntity"](contained_type)

        results: list["ASTEntity"] = []
        for raw in value:
            try:
                results.append(
                    adapter.validate_python(raw, context=validation_info.context)  # pyright: ignore[reportArgumentType] -- bad type defs?
                )
            except ValidationError as exc:
                context.broken_tasks.append(BrokenTask(raw=raw, reason=str(exc)))

        return results
