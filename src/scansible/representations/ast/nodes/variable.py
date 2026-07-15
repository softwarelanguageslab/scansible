"""AST nodes to represent variables and variable files."""

from __future__ import annotations

from typing import Annotated, override

from collections.abc import Mapping

from pydantic import Field

from scansible.types import AnyValue
from scansible.utils import ProjectPath

from .._normalizers import NormalizeNone
from .._validators import Identifier
from ..common import ExtractionContext, parse_file
from .base import ASTFile


class VariableFile(ASTFile, frozen=True):
    """Represents a file containing variables (role `defaults/`, `vars/`, and playbook `vars_files`)."""

    #: The variables contained within the file. The order is irrelevant.
    variables: Annotated[Mapping[Identifier, AnyValue], NormalizeNone] = Field(
        default_factory=dict
    )

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> VariableFile:
        """Load and parse a variable file from the given path."""
        return cls.model_validate(
            {"path": path.relative, "variables": parse_file(path)}, context=context
        )
