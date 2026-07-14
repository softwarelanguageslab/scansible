"""Loaders for Ansible objects.

The loaders generally return a tuple of two values: The loaded, validated and
transformed data structure (possibly as an Ansible object), and the original
parsed data structure without modifications.
"""

from __future__ import annotations

from typing import cast, final

import types
from collections.abc import Sequence
from copy import deepcopy
from pathlib import Path

from ansible.parsing.yaml.objects import AnsibleMapping, AnsibleUnicode

from . import ansible_types as ans
from .helpers import ProjectPath, parse_file, validate_ansible_object


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


def _transform_old_become(ds: dict[str, ans.AnsibleValue]) -> None:
    # Current Ansible version refuses to parse tasks that use sudo/su and their
    # derivatives (*_user, *_exe, *_flags, *_pass). Transform them like legacy
    # Ansible versions used to do.
    # https://github.com/ansible/ansible/commit/e40832df847bc7dcc94f41c491618de665c0b9e5

    # Same validation as legacy Ansible versions
    has_become = "become" in ds or "become_user" in ds
    has_sudo = "sudo" in ds or "sudo_user" in ds
    has_su = "su" in ds or "su_user" in ds

    if not (has_sudo or has_su):
        # Nothing to transform.
        return

    # At most one become method may be present.
    if sum(1 for has_method in (has_become, has_sudo, has_su) if has_method) > 1:
        raise LoadError(
            "task", "Invalid mix of directives: sudo/su/become", extra_msg=repr(ds)
        )

    sudo_kws = ("sudo", "sudo_user", "sudo_exe", "sudo_flags", "sudo_pass")
    su_kws = ("su", "su_user", "su_exe", "su_flags", "su_pass")
    main_kw, user_kw, exe_kw, flags_kw, pass_kw = sudo_kws if has_sudo else su_kws

    ds["become_method"] = AnsibleUnicode("sudo" if has_sudo else "su")

    if main_kw in ds:
        ds["become"] = ds[main_kw]
        del ds[main_kw]
    if user_kw in ds:
        ds["become_user"] = ds[user_kw]
        del ds[user_kw]
    if exe_kw in ds:
        ds["become_exe"] = ds[exe_kw]
        del ds[exe_kw]
    if flags_kw in ds:
        ds["become_flags"] = ds[flags_kw]
        del ds[flags_kw]
    if pass_kw in ds:
        # There's no `become_pass` alternative, so define the variable instead.
        variables = cast(AnsibleMapping, ds.get("vars", {}))
        variables["ansible_become_password"] = ds[pass_kw]
        ds["vars"] = variables
        del ds[pass_kw]


@final
class _PatchedPlay(ans.Play):
    tasks: Sequence[dict[str, ans.AnsibleValue]]  # pyright: ignore[reportIncompatibleVariableOverride]
    handlers: Sequence[dict[str, ans.AnsibleValue]]  # pyright: ignore[reportIncompatibleVariableOverride]
    pre_tasks: Sequence[dict[str, ans.AnsibleValue]]  # pyright: ignore[reportIncompatibleVariableOverride]
    post_tasks: Sequence[dict[str, ans.AnsibleValue]]  # pyright: ignore[reportIncompatibleVariableOverride]
    roles: Sequence[str | dict[str, ans.AnsibleValue]]  # pyright: ignore[reportIncompatibleVariableOverride]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # Similar to _PatchedBlock, remove loaders for tasks, handlers, and
        # roles because of Ansible's eager processing.
        self._load_tasks = None
        self._load_pre_tasks = None
        self._load_post_tasks = None
        self._load_handlers = None
        self._load_roles = None


# Workaround for error messages using the wrong class name.
_PatchedPlay.__name__ = "Play"


def load_play(original_ds: dict[str, ans.AnsibleValue]) -> tuple[_PatchedPlay, object]:
    ds = deepcopy(original_ds)

    _transform_old_become(ds)

    # remove the "accelerate" key if present. It was removed in 2.4
    _ = ds.pop("accelerate", None)

    if "vars_files" in ds and ds["vars_files"] is None:
        del ds["vars_files"]

    raw_play = _PatchedPlay()
    _ = raw_play.load_data(ds)
    validate_ansible_object(raw_play)

    return raw_play, original_ds


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


@final
class _PatchedRoleInclude(ans.role.RoleInclude):
    # Override the _load_role_path method so that it doesn't resolve the path.
    def _load_role_path(self, role_name: str) -> tuple[str, str]:  # pyright: ignore[reportUnusedFunction]
        return role_name, ""


_PatchedRoleInclude.__name__ = "RoleInclude"


def load_role_dependency(
    original_ds: str | dict[str, ans.AnsibleValue], allow_new_style: bool = False
) -> tuple[_PatchedRoleInclude, dict[str, str] | None, object]:
    ds = deepcopy(original_ds)

    if isinstance(ds, dict):
        _transform_old_become(ds)

    if isinstance(ds, dict) and not ("name" in ds or "role" in ds) and allow_new_style:
        # new-style role dependency, needs to be parsed specially and converted
        # to old style for later loading.
        parsed_def = ans.role.RoleRequirement.role_yaml_parse(cast(AnsibleMapping, ds))
        if "name" in parsed_def:
            ds["name"] = AnsibleUnicode(parsed_def["name"])
    else:
        parsed_def = None

    return _load_old_style_role_dependency(ds), parsed_def, original_ds


def _load_old_style_role_dependency(
    original_ds: str | dict[str, ans.AnsibleValue],
) -> _PatchedRoleInclude:
    ds = deepcopy(original_ds)

    # Validation from original RoleInclude, can't use the method because it
    # constructs a RoleInclude, which attempts to resolve the role path.
    if not isinstance(ds, (str, dict, ans.AnsibleBaseYAMLObject, int)):  # pyright: ignore[reportUnnecessaryIsInstance]
        raise LoadTypeError(
            "role dependency", str | dict | ans.AnsibleBaseYAMLObject, ds
        )

    if isinstance(ds, str) and "," in ds:
        raise LoadError(
            "role dependency", "Invalid old-style role requirement", extra_msg=repr(ds)
        )

    ri = _PatchedRoleInclude()
    _ = ri.load_data(ds)
    validate_ansible_object(ri)

    return ri
