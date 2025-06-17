"""Loaders for Ansible objects.

The loaders generally return a tuple of two values: The loaded, validated and
transformed data structure (possibly as an Ansible object), and the original
parsed data structure without modifications.
"""

from __future__ import annotations

import types
from collections.abc import Sequence
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path
from typing import Any, Generator, Literal, Type, cast, overload

from ansible.parsing import mod_args

from scansible.utils import actions

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


def _type_to_str(type_: Any) -> str:
    if isinstance(type_, types.GenericAlias):
        return str(type_)
    return type_.__name__ if hasattr(type_, "__name__") else str(type_)  # type: ignore[no-any-return]


class LoadTypeError(LoadError):
    """Raised when loading led to a wrong type."""

    #: The expected type.
    expected_type: Any
    #: The actual type.
    actual_type: Type[Any]
    #: The actual object.
    actual_value: Any

    def __init__(
        self,
        object_type: str,
        expected_type: Any,
        actual_value: Any,
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


def load_role_metadata(path: ProjectPath) -> tuple[dict[str, ans.AnsibleValue], Any]:
    """Load role metadata, return tuple of validated and original data."""
    original_ds = parse_file(path)
    ds = deepcopy(original_ds)

    # Need to do the validation ourselves because role metadata parsing is
    # heavily under-validated in Ansible.
    if not ds:
        raise LoadError("role metadata", "Empty metadata", path.relative)
    if not isinstance(ds, dict):
        raise LoadTypeError("role metadata", dict, ds, path.relative)

    ds = cast(dict[str, "ans.AnsibleValue"], ds)

    _validate_meta_galaxy_info(ds)
    _load_meta_platforms(ds)
    _load_meta_dependencies(ds)

    return ds, original_ds


def _validate_meta_galaxy_info(ds: dict[str, ans.AnsibleValue]) -> None:
    galaxy_info = ds.get("galaxy_info")
    if galaxy_info is None:
        ds["galaxy_info"] = ans.AnsibleMapping()
        return

    if not isinstance(galaxy_info, dict):
        raise LoadTypeError("role metadata galaxy_info", dict, galaxy_info)


def _load_meta_platforms(ds: dict[str, ans.AnsibleValue]) -> None:
    assert isinstance(ds["galaxy_info"], dict)
    platforms = ds["galaxy_info"].get("platforms")
    if platforms is None:
        ds["galaxy_info"]["platforms"] = ans.AnsibleSequence()
        return

    # Validation based on Ansible Galaxy loader
    # https://github.com/ansible/galaxy/blob/1fe0bd986aaeb4c45157d4e463b7049cad76a25e/galaxy/importer/loaders/role.py#L188
    # https://github.com/ansible/galaxy/blob/1fe0bd986aaeb4c45157d4e463b7049cad76a25e/galaxy/importer/loaders/role.py#L464
    if not isinstance(platforms, (tuple, list)):
        raise LoadTypeError("role metadata galaxy_info.platforms", list, platforms)

    validated_platforms = ans.AnsibleSequence()
    for platform in cast(Sequence[Any], platforms):
        if not isinstance(platform, dict):
            print(
                f"Ignoring malformed platform {platform!r}: expected to be dict, got {_type_to_str(type(platform))}"
            )
            continue

        platform = cast(dict[str, Any], platform)
        name = platform.get("name")
        versions = platform.get("versions", ["all"])
        # https://github.com/ansible/galaxy/blob/1fe0bd986aaeb4c45157d4e463b7049cad76a25e/galaxy/importer/loaders/role.py#L471
        # ["any", "all"] is equivalent to ["all"]. Also, Ansible Galaxy doesn't
        # verify whether versions is actually a list, so if it's the string
        # "small", it'd still be considered ["all"].
        if isinstance(versions, (list, str, dict)) and "all" in versions:
            versions = ["all"]

        if not name:
            print(f'Ignoring malformed platform {platform!r}: missing "name" key')
            continue

        if not isinstance(versions, list):
            print(
                f'Ignoring malformed platform {platform!r}: "versions" expected to be list, got {_type_to_str(type(versions))}'
            )
            continue

        validated_platforms.append(
            ans.AnsibleMapping(
                {
                    "name": str(name),  # type: ignore[dict-item]
                    "versions": [str(v) for v in versions],  # type: ignore[dict-item]
                }
            )
        )

    ds["galaxy_info"]["platforms"] = validated_platforms


def _load_meta_dependencies(ds: dict[str, ans.AnsibleValue]) -> None:
    dependencies = ds.get("dependencies")
    if dependencies is None:
        ds["dependencies"] = ans.AnsibleSequence()
        return

    if not isinstance(dependencies, list):
        raise LoadTypeError("role dependencies", list, dependencies)


def load_variable_file(path: ProjectPath) -> tuple[dict[str, ans.AnsibleValue], Any]:
    original_ds = parse_file(path)
    ds = deepcopy(original_ds)

    if ds is None:
        ds = ans.AnsibleMapping()

    if not isinstance(ds, dict):
        raise LoadTypeError("variable file", dict, ds, path.relative)

    ds = cast(dict["ans.AnsibleValue", "ans.AnsibleValue"], ds)
    for var_name in ds:
        if not isinstance(var_name, str):
            raise LoadTypeError("variable name", str, var_name, path.relative)

    return cast(dict[str, "ans.AnsibleValue"], ds), original_ds


def load_tasks_file(path: ProjectPath) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
    original_ds = parse_file(path)
    ds = deepcopy(original_ds)

    if ds is None:
        ds = ans.AnsibleSequence()

    if not isinstance(ds, list):
        raise LoadTypeError("task file", list, ds, path.relative)

    ds = cast(list["ans.AnsibleValue"], ds)
    for content in ds:
        if not isinstance(content, dict) or not all(
            isinstance(prop, str) for prop in content
        ):
            raise LoadTypeError(
                "task file content", dict[str, Any], content, path.relative
            )

    return cast(list[dict[str, "ans.AnsibleValue"]], ds), original_ds


@contextmanager
def _patch_modargs_parser() -> Generator[None, None, None]:
    # Patch the ModuleArgsParser so that it doesn't verify whether the action exist.
    # Otherwise it'll complain on non-builtin actions
    old_mod_args_parse = ans.ModuleArgsParser.parse
    ans.ModuleArgsParser.parse = (
        lambda self, skip_action_validation=False: old_mod_args_parse(
            self, skip_action_validation=True
        )
    )  # type: ignore[assignment]

    try:
        yield
    finally:
        ans.ModuleArgsParser.parse = old_mod_args_parse  # type: ignore[assignment]


@contextmanager
def _patch_lookup_loader() -> Generator[None, None, None]:
    # Patch the lookup_loader so that it always reports a lookup plugin as existing.
    # Ansible does early resolution of `with_*` lookups, and since we may not
    # have all collections installed and we're not registering custom lookup
    # plugins, it'll complain when those are used in `with_*` directives.
    old_loader_has_plugin = ans.PluginLoader.has_plugin
    ans.PluginLoader.has_plugin = lambda *args, **kwargs: True  # type: ignore[assignment]
    ans.PluginLoader.__contains__ = lambda *args, **kwargs: True  # type: ignore[assignment]

    try:
        yield
    finally:
        ans.PluginLoader.has_plugin = old_loader_has_plugin  # type: ignore[assignment]
        ans.PluginLoader.__contains__ = old_loader_has_plugin  # type: ignore[assignment]


def _get_task_action(ds: dict[str, ans.AnsibleValue]) -> str:
    # Ansible raises an error if _raw_params is present for actions that don't support
    # it, and they removed `include` from the possible modules that support it, so add it
    # back.
    mod_args.RAW_PARAM_MODULES = mod_args.RAW_PARAM_MODULES | {"include"}
    fixed_ds = {key: value for key, value in ds.items() if key != "_raw_params"}
    args_parser = ans.ModuleArgsParser(fixed_ds)
    (action, _, _) = args_parser.parse()
    return action


def _transform_task_static_include(
    ds: dict[str, ans.AnsibleValue], action: str
) -> None:
    # Current Ansible version crashes when the old static key is used.
    # Transform it to modern syntax, either into `import_tasks` if it's a
    # static include, or `include_tasks` if it isn't.
    if "static" in ds:
        is_static = ds["static"] is not None and ans.convert_bool(ds["static"])

        del ds["static"]
        if actions.is_bare_include(action):
            include_args = ds["include"]
            del ds["include"]
            if is_static:
                ds["import_tasks"] = include_args
            else:
                ds["include_tasks"] = include_args
        elif actions.is_include_tasks(action) and is_static:
            raise LoadError(
                "task", "include_tasks with static: yes", extra_msg=repr(ds)
            )
        elif actions.is_import_tasks(action) and not is_static:
            raise LoadError("task", "import_tasks with static: no", extra_msg=repr(ds))


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

    ds["become_method"] = "sudo" if has_sudo else "su"  # type: ignore[assignment]

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
        variables: dict[str, ans.AnsibleValue] = ds.get("vars", {})  # type: ignore[assignment]
        variables["ansible_become_password"] = ds[pass_kw]
        ds["vars"] = variables  # type: ignore[assignment]
        del ds[pass_kw]


def _transform_old_always_run(ds: dict[str, ans.AnsibleValue]) -> None:
    # `always_run` is an old, now-removed directive which has since been
    # replaced by the `check_mode: no` directive.
    if "always_run" in ds:
        try:
            val = ans.convert_bool(ds["always_run"])
        except Exception as e:
            print(f'Could not load "always_run" value: {e}')
            return

        # if `always_run: yes` -> `check_mode: no`.
        # not sure if `always_run: no` necessarily means `check_mode: yes` or
        # just "use default behaviour".
        del ds["always_run"]
        if val:
            ds["check_mode"] = False


@overload
def load_task(
    original_ds: dict[str, ans.AnsibleValue] | None, as_handler: Literal[True]
) -> tuple[ans.Handler, Any]: ...


@overload
def load_task(
    original_ds: dict[str, ans.AnsibleValue] | None, as_handler: Literal[False]
) -> tuple[ans.Task, Any]: ...


def load_task(
    original_ds: dict[str, ans.AnsibleValue] | None, as_handler: bool
) -> tuple[ans.Task | ans.Handler, Any]:
    ds = deepcopy(original_ds)

    # Apparently an empty Task is allowed by Ansible.
    if ds is None:
        ds = {}

    # Need to do this before mod_args parsing, since mod_args parsing can crash
    # because of the presence of old keywords.
    _transform_old_become(ds)
    _transform_old_always_run(ds)

    with _patch_modargs_parser(), _patch_lookup_loader():
        action = _get_task_action(ds)
        is_include_tasks = actions.is_import_include_tasks(action)

        if actions.is_import_playbook(action):
            # This loader only gets called for tasks in task lists, so an
            # import_playbook is illegal here.
            raise LoadError(
                "task", "import_playbook is only allowed as a top-level playbook task"
            )

        if actions.is_import_include_tasks(action):
            # Check for include/import tasks and transform them if the static
            # directive is present.
            _transform_task_static_include(ds, action)

        # This can happen and Ansible doesn't do anything about it, it just
        # ignores the when. Remove the directive so that defaults take over.
        if "when" in ds and ds["when"] is None:
            del ds["when"]

        # Use the correct Ansible representation so that more validation is done.
        ansible_cls: Type[ans.Task]
        if actions.is_import_include_role(action):
            ansible_cls = ans.IncludeRole
        elif not as_handler:
            ansible_cls = ans.Task if not is_include_tasks else ans.TaskInclude
        else:
            ansible_cls = (
                ans.Handler if not is_include_tasks else ans.HandlerTaskInclude
            )

        raw_task = ansible_cls.load(ds)
        validate_ansible_object(raw_task)

    return raw_task, original_ds


class _PatchedBlock(ans.Block):
    block: list[dict[str, ans.AnsibleValue]]  # type: ignore[assignment]
    rescue: list[dict[str, ans.AnsibleValue]]  # type: ignore[assignment]
    always: list[dict[str, ans.AnsibleValue]]  # type: ignore[assignment]

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)
        # Remove the loaders from the block implementation, since they dispatch
        # to ansible.playbook.helpers.load_list_of_tasks, which does eager
        # loading of import_* tasks and inlines the imported roles/tasks into
        # the block. We don't want that to happen.
        self._load_block = None
        self._load_rescue = None
        self._load_always = None


# Workaround for error messages using the wrong class name.
_PatchedBlock.__name__ = "Block"


def load_block(original_ds: dict[str, ans.AnsibleValue]) -> tuple[_PatchedBlock, Any]:
    ds = deepcopy(original_ds)

    _transform_old_become(ds)

    if not _PatchedBlock.is_block(ds):
        raise LoadError(
            "block",
            "Not a block",
            extra_msg=f'Expected block to contain "block" keyword, but it does not.\n\n{ds!r}',
        )

    raw_block = _PatchedBlock(ds)
    raw_block.load_data(ds)
    validate_ansible_object(raw_block)

    return raw_block, ds


class _PatchedPlay(ans.Play):
    tasks: list[dict[str, ans.AnsibleValue]]  # type: ignore[assignment]
    handlers: list[dict[str, ans.AnsibleValue]]  # type: ignore[assignment]
    pre_tasks: list[dict[str, ans.AnsibleValue]]  # type: ignore[assignment]
    post_tasks: list[dict[str, ans.AnsibleValue]]  # type: ignore[assignment]
    roles: list[str | dict[str, ans.AnsibleValue]]  # type: ignore[assignment]

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


def load_play(original_ds: dict[str, ans.AnsibleValue]) -> tuple[_PatchedPlay, Any]:
    ds = deepcopy(original_ds)

    _transform_old_become(ds)

    # remove the "accelerate" key if present. It was removed in 2.4
    ds.pop("accelerate", None)

    if "vars_files" in ds and ds["vars_files"] is None:
        del ds["vars_files"]

    raw_play = _PatchedPlay()
    raw_play.load_data(ds)
    validate_ansible_object(raw_play)

    return raw_play, original_ds


def load_playbook(path: ProjectPath) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
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


class _PatchedRoleInclude(ans.role.RoleInclude):
    # Override the _load_role_path method so that it doesn't resolve the path.
    def _load_role_path(self, role_name: str) -> tuple[str, str]:
        return role_name, ""


_PatchedRoleInclude.__name__ = "RoleInclude"


def load_role_dependency(
    original_ds: str | dict[str, ans.AnsibleValue], allow_new_style: bool = False
) -> tuple[_PatchedRoleInclude, dict[str, str] | None, Any]:
    ds = deepcopy(original_ds)

    if isinstance(ds, dict):
        _transform_old_become(ds)

    if isinstance(ds, dict) and not ("name" in ds or "role" in ds) and allow_new_style:
        # new-style role dependency, needs to be parsed specially and converted
        # to old style for later loading.
        parsed_def = ans.role.RoleRequirement.role_yaml_parse(ds)  # type: ignore[arg-type]
        if "name" in parsed_def:
            ds["name"] = parsed_def["name"]  # type: ignore[assignment]
    else:
        parsed_def = None

    return _load_old_style_role_dependency(ds), parsed_def, original_ds


def _load_old_style_role_dependency(
    original_ds: str | dict[str, ans.AnsibleValue],
) -> _PatchedRoleInclude:
    ds = deepcopy(original_ds)

    # Validation from original RoleInclude, can't use the method because it
    # constructs a RoleInclude, which attempts to resolve the role path.
    if not isinstance(ds, (str, dict, ans.AnsibleBaseYAMLObject, int)):  # pyright: ignore
        raise LoadTypeError(
            "role dependency", str | dict | ans.AnsibleBaseYAMLObject, ds
        )

    if isinstance(ds, str) and "," in ds:
        raise LoadError(
            "role dependency", "Invalid old-style role requirement", extra_msg=repr(ds)
        )

    ri = _PatchedRoleInclude()
    ri.load_data(ds)
    validate_ansible_object(ri)

    return ri
