"""Reusable validation constraints for use as model field types."""

from __future__ import annotations

from typing import Annotated

import keyword
from pathlib import Path

from pydantic import AfterValidator


def _validate_relative_path(path: Path) -> Path:
    """Validate whether the given path is a relative path.

    Note that we do not validate whether it is relative to any particular
    directory.
    """
    if path.is_absolute():
        raise ValueError(f"Expected relative path, got {path}")
    return path


def _validate_absolute_path(path: Path) -> Path:
    """Validate whether the given path is an absolute path."""
    if not path.is_absolute():
        raise ValueError(f"Expected absolute path, got {path}")
    return path


def _validate_identifier(value: str) -> str:
    """Validate whether the given value is a valid identifier.

    Logic mirrors Ansible's own logic in `ansible.utils.vars.isidentifier`.
    """
    if not (value.isascii() and value.isidentifier()):
        raise ValueError(f"Expected a valid identifier, got {value}")
    if keyword.iskeyword(value):
        raise ValueError(f"{value} is a reserved keyword")
    return value


#: Relative paths in the project.
type RelativePath = Annotated[Path, AfterValidator(_validate_relative_path)]

#: Absolute paths in the project.
type AbsolutePath = Annotated[Path, AfterValidator(_validate_absolute_path)]

#: Identifiers in Ansible files, e.g., variable names.
type Identifier = Annotated[str, AfterValidator(_validate_identifier)]
