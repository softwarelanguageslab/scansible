"""Base classes shared by all AST nodes."""

from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, Self, Unpack, override

from abc import ABC, abstractmethod

from pydantic import BaseModel, ConfigDict, Field, model_validator

from scansible.cst import YamlMap
from scansible.utils import Location, ProjectPath

from .._validators import RelativePath  # noqa: TC001 -- For Pydantic

if TYPE_CHECKING:
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

    #: The source code location of the node.
    location: Location = Field(default_factory=Location.synthetic, alias="__location__")

    @classmethod
    @override
    def __pydantic_init_subclass__(cls, **kwargs: Unpack[ConfigDict]) -> None:
        """Set the `model_directives` field after Pydantic builds the model."""
        super().__pydantic_init_subclass__(**kwargs)
        cls.model_directives = {
            field.alias or name
            for name, field in cls.model_fields.items()
            # Location is internal.
            if name != "location"
        }

    @model_validator(mode="before")
    @classmethod
    def _inject_location(cls, data: object) -> object:
        """Extract source code location information from Ansible objects and present it to the model for validation."""
        if isinstance(data, YamlMap):
            data["__location__"] = data.__location__

        return data  # pyright: ignore[reportUnknownVariableType]

    @model_validator(mode="after")
    def _alias_location(self) -> Self:
        """Alias the `location` property to `__location__` to adhere to the `HasLocation` protocol.

        This workaround is necessary because Pydantic does not allow attributes to start with __.
        Note that we're not subclassing the `HasLocation` trait because it causes a metaclass conflict.
        """
        self.__location__: Location = self.location  # pyright: ignore[reportAttributeAccessIssue] -- Frozen but still works at this point.
        return self

    @property
    def model_directives_set(self) -> set[str]:
        """Get the set of directives that are defined on this entity.

        Note that these may not directly correspond to the attribute names due to aliases.
        """
        return {
            self.__class__.model_fields[name].alias or name
            for name in self.model_fields_set
            # Location is internal.
            if name != "location"
        }


__all__ = [
    "ASTEntity",
    "ASTFile",
    "ASTNode",
]
