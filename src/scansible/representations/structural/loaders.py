"""Loaders for Ansible objects.

The loaders generally return a tuple of two values: The loaded, validated and
transformed data structure (possibly as an Ansible object), and the original
parsed data structure without modifications.
"""

from __future__ import annotations

from typing import cast

import types
from copy import deepcopy
from pathlib import Path

from . import ansible_types as ans
from .helpers import ProjectPath, parse_file


class LoadError(Exception):
    """Raised when loading or validation failed."""

    #: The type of object that was being loaded.
    object_type: str
    #: Reason loading or validation failed.
    reason: str
    #: Relative path to the file that caused the error, if available.
    file_path: Path | None

    def __init__(
        self,
        object_type: str,
        reason: str,
        file_path: Path | None = None,
        extra_msg: str = "",
    ) -> None:
        if file_path:
            msg = f"Failed to load {object_type} at {file_path}: {reason}"
        else:
            msg = f"Failed to load {object_type}: {reason}"

        if extra_msg:
            msg = f"{msg}\n\n{extra_msg}"

        super().__init__(msg)
        self.object_type = object_type
        self.reason = reason
        self.file_path = file_path


def _type_to_str(type_: type | types.UnionType) -> str:
    if isinstance(type_, (types.GenericAlias, types.UnionType)):
        return str(type_)
    return type_.__name__ if hasattr(type_, "__name__") else str(type_)


class LoadTypeError(LoadError):
    """Raised when loading led to a wrong type."""

    #: The expected type.
    expected_type: type | types.UnionType
    #: The actual type.
    actual_type: type
    #: The actual object.
    actual_value: object

    def __init__(
        self,
        object_type: str,
        expected_type: type | types.UnionType,
        actual_value: object,
        file_path: Path | None = None,
    ) -> None:
        extra_msg = f"Expected {object_type} to be {_type_to_str(expected_type)}, got {_type_to_str(type(actual_value))} instead.\nActual value:\n{actual_value!r}"
        super().__init__(
            object_type,
            "Wrong type encountered",
            file_path=file_path,
            extra_msg=extra_msg,
        )
        self.expected_type = expected_type
        self.actual_type = type(actual_value)
        self.actual_value = actual_value


def load_playbook(
    path: ProjectPath,
) -> tuple[list[dict[str, ans.AnsibleValue]], object]:
    original_ds = parse_file(path)
    ds = deepcopy(original_ds)

    if not ds:
        raise LoadError("playbook", "Empty playbook", path.relative)
    if not isinstance(ds, list):
        raise LoadTypeError("playbook", list, ds, path.relative)

    ds = cast(list["ans.AnsibleValue"], ds)

    # Transform old include action into import_playbook
    for child in ds:
        if not isinstance(child, dict):
            raise LoadTypeError("playbook entry", dict, ds, path.relative)
        if "include" in child:
            child["import_playbook"] = child.pop("include")

    return cast(list[dict[str, "ans.AnsibleValue"]], ds), original_ds
