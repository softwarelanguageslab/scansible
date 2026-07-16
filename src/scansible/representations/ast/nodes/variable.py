"""AST nodes to represent variables and variable files."""

from __future__ import annotations

from typing import override

from collections.abc import Mapping

from pydantic import Field

from scansible.types import AnyValue, ScalarValue
from scansible.utils import FrozenDict, ProjectPath

from ..common import ExtractionContext, parse_file
from .base import ASTFile


class VariableFile(ASTFile, frozen=True):
    """Represents a file containing variables (role `defaults/`, `vars/`, and playbook `vars_files`)."""

    #: The variables contained within the file. The order is irrelevant. Note that, contrary to play/task/block vars,
    #: variable names in variable files are not validated as identifiers, and Ansible accepts any scalar value as the
    #: variable name.
    variables: Mapping[ScalarValue, AnyValue] = Field(
        default_factory=FrozenDict[ScalarValue, AnyValue]
    )

    @classmethod
    @override
    def load(cls, path: ProjectPath, context: ExtractionContext) -> VariableFile:
        """Load and parse a variable file from the given path."""
        return cls.model_validate(
            {"path": path.relative, "variables": parse_file(path)}, context=context
        )
