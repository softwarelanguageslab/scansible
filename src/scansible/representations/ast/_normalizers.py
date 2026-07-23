"""Reusable field-normalization logic.

Each `Normalizer` implements one normalization rule (e.g. wrapping a scalar into a single-element list).
Normalizers are attached to a model field via `Annotated[T, SomeNormalizer]` and are applied by
`ASTEntity` before Pydantic validates the field's value.
"""

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


class Lenient(Normalizer):
    """Normalizer that enables parsing in sequences to be lenient.

    If the lenient flag is set in the validation context, this normalizer will catch
    any item-specific validation errors and ignore it, omitting that item from the
    resulting list. In non-lenient (strict) mode, the validator acts normally.
    """

    @classmethod
    def _get_contained_type(cls, field_info: FieldInfo) -> type[object]:
        """Extract the element type from a `Sequence[...]` field annotation."""
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
        """Validate each item, dropping ones that fail when lenient."""
        if value == None:  # noqa: E711 -- could be YamlNone
            return value

        if not isinstance(value, Sequence) or isinstance(value, (str, bytes)):
            # Not exactly lenient, but all usages of lenient sequence expect real sequences (e.g., a task sequence does not accept a single task).
            raise ValueError("Expected a sequence")

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
                context.broken_tasks.append(BrokenTask(raw=raw, reason=exc))

        return results
