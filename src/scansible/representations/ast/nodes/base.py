"""Base classes shared by all AST nodes."""

from __future__ import annotations

from typing import Self, cast

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator
from pydantic_core import PydanticUndefined

from scansible.utils import ProjectPath

from .._normalizers import Normalizer
from .._validators import RelativePath
from ..common import ExtractionContext, Position


class ASTEntity(BaseModel, strict=True, frozen=True, extra="forbid"):
    """Base class inherited by all classes participating in the AST representation."""

    @field_validator("*", mode="before")
    @classmethod
    def _normalize(cls, value: object, info: ValidationInfo) -> object:
        """Apply the declared normalizations to field values."""

        assert info.field_name is not None
        field_info = cls.model_fields[info.field_name]

        # If given an explicit `None`, always convert it to the directive's default.
        # This is what Ansible seem to do _most_ of the time. It's possible that Ansible
        # rejects some `None` values in certain cases, in such cases Scansible is possibly
        # slightly more lenient, but that's okay.
        if value is None:
            default = cast(
                object,
                field_info.get_default(call_default_factory=True, validated_data=value),
            )
            if default is not PydanticUndefined:
                value = default

        for meta in field_info.metadata:  # pyright: ignore[reportAny]
            if isinstance(meta, Normalizer) or (
                isinstance(meta, type) and issubclass(meta, Normalizer)
            ):
                value = meta.normalize(value, field_info, info)

        return value


class ASTFile(ASTEntity, ABC, frozen=True):
    """Base class inherited by all files represented by an AST."""

    #: The relative path to the file in the project.
    path: RelativePath

    @classmethod
    @abstractmethod
    def load(cls: type[Self], path: ProjectPath, context: ExtractionContext) -> Self:
        """Construct the representation for a file by parsing the given path."""
        ...


class ASTNode(ASTEntity, frozen=True):
    """Base class inherited by all nodes inside of an AST for a file."""

    #: The source code position of the node.
    position: Position = Field(default_factory=Position)

    @model_validator(mode="before")
    @classmethod
    def _inject_position(cls, data: object) -> object:
        """Extract source code position information from Ansible objects and present it to the model for validation."""

        if hasattr(data, "ansible_pos"):
            pos = getattr(data, "ansible_pos")  # pyright: ignore[reportAny]
            if isinstance(data, dict):
                data["position"] = pos

        return data  # pyright: ignore[reportUnknownVariableType]
