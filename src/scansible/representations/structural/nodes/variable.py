from __future__ import annotations

from typing import Annotated, override

from collections.abc import Mapping

from pydantic import Field

from scansible.types import AnyValue

from .._normalizers import NormalizeNone
from .._validators import Identifier
from ..common import ExtractionContext
from ..helpers import ProjectPath, parse_file
from .base import ASTFile


class VariableFile(ASTFile, frozen=True):
    """Represents a file containing variables."""

    #: The variables contained within the file. The order is irrelevant.
    variables: Annotated[Mapping[Identifier, AnyValue], NormalizeNone] = Field(
        default_factory=dict
    )

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> VariableFile:
        return cls.model_validate(
            {"path": path.relative, "variables": parse_file(path)}, context=context
        )
