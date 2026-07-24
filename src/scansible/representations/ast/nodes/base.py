"""Base classes shared by all AST nodes."""

from __future__ import annotations

from typing import Self

from abc import ABC, abstractmethod

from pydantic import BaseModel, Field, ValidationInfo, field_validator, model_validator

from scansible.representations.cst import YamlMap
from scansible.utils import Position, ProjectPath

from .._normalizers import Normalizer
from .._validators import RelativePath
from ..common import ExtractionContext


class ASTEntity(BaseModel, strict=True, frozen=True, extra="forbid"):
    """Base class inherited by all classes participating in the AST representation."""

    @field_validator("*", mode="before")
    @classmethod
    def _normalize(cls, value: object, info: ValidationInfo) -> object:
        """Apply the declared normalizations to field values."""

        assert info.field_name is not None
        field_info = cls.model_fields[info.field_name]

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
    position: Position = Field(default_factory=Position.synthetic)

    @model_validator(mode="before")
    @classmethod
    def _inject_position(cls, data: object) -> object:
        """Extract source code position information from Ansible objects and present it to the model for validation."""
        if isinstance(data, YamlMap):
            data["position"] = data.__position__

        return data  # pyright: ignore[reportUnknownVariableType]

    @model_validator(mode="after")
    def _alias_position(self) -> Self:
        """Alias the `position` property to `__position__` to adhere to the `Positioned` protocol.

        This workaround is necessary because Pydantic does not allow attributes to start with __.
        Note that we're not subclassing the `Positioned` trait because it causes a metaclass conflict.
        """
        self.__position__: Position = self.position  # pyright: ignore[reportAttributeAccessIssue] -- Frozen but still works at this point.
        return self
