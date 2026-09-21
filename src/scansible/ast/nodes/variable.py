"""AST nodes to represent variables and variable files."""

from __future__ import annotations

from typing import override

from pydantic import Field

from scansible.cst import parse_file
from scansible.utils import ProjectPath

from ..common import ExtractionContext
from .base import ASTFile
from .expression import AnyExpression, MapLiteral, ScalarLiteral


class VariableFile(ASTFile, frozen=True):
    """Represents a file containing variables (role `defaults/`, `vars/`, and playbook `vars_files`)."""

    #: The variables contained within the file. The order is irrelevant. Note that, contrary to play/task/block vars,
    #: variable names in variable files are not validated as identifiers, and Ansible accepts any scalar value as the
    #: variable name.
    variables: MapLiteral[ScalarLiteral, AnyExpression] = Field(
        default_factory=MapLiteral
    )

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> VariableFile:
        """Load and parse a variable file from the given path."""
        return cls.model_validate(
            {"path": path.relative, "variables": parse_file(path)}, context=context
        )


__all__ = ["VariableFile"]
