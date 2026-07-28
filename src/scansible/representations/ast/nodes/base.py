"""Base classes shared by all AST nodes."""

from __future__ import annotations

from typing import ClassVar, Self, Unpack, override

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scansible.representations.cst import YamlMap
from scansible.utils import Position, ProjectPath

from .._validators import RelativePath
from ..common import ExtractionContext


class ASTEntity(BaseModel, strict=True, frozen=True, extra="forbid"):
    """Base class inherited by all classes participating in the AST representation."""


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

    #: The set of directives that are supported by this entity. Note that these may not directly correspond to the attribute names due to aliases.
    model_directives: ClassVar[set[str]]

    #: The source code position of the node.
    position: Position = Field(default_factory=Position.synthetic, alias="__position__")

    @classmethod
    @override
    def __pydantic_init_subclass__(cls, **kwargs: Unpack[ConfigDict]) -> None:
        """Set the `model_directives` field after Pydantic builds the model."""
        super().__pydantic_init_subclass__(**kwargs)
        cls.model_directives = {
            field.alias or name
            for name, field in cls.model_fields.items()
            # Position is internal.
            if name != "position"
        }

    @model_validator(mode="before")
    @classmethod
    def _inject_position(cls, data: object) -> object:
        """Extract source code position information from Ansible objects and present it to the model for validation."""
        if isinstance(data, YamlMap):
            data["__position__"] = data.__position__

        return data  # pyright: ignore[reportUnknownVariableType]

    @model_validator(mode="after")
    def _alias_position(self) -> Self:
        """Alias the `position` property to `__position__` to adhere to the `Positioned` protocol.

        This workaround is necessary because Pydantic does not allow attributes to start with __.
        Note that we're not subclassing the `Positioned` trait because it causes a metaclass conflict.
        """
        self.__position__: Position = self.position  # pyright: ignore[reportAttributeAccessIssue] -- Frozen but still works at this point.
        return self

    @property
    def model_directives_set(self) -> set[str]:
        """Get the set of directives that are defined on this entity.

        Note that these may not directly correspond to the attribute names due to aliases.
        """
        return {
            self.__class__.model_fields[name].alias or name
            for name in self.model_fields_set
            # Position is internal.
            if name != "position"
        }


__all__ = [
    "ASTEntity",
    "ASTFile",
    "ASTNode",
]
