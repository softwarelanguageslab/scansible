"""Loaders for Ansible objects.

The loaders generally return a tuple of two values: The loaded, validated and
transformed data structure (possibly as an Ansible object), and the original
parsed data structure without modifications.
"""

from __future__ import annotations

from typing import Any, Generator, Literal, Type, overload

import types
from contextlib import contextmanager
from copy import deepcopy
from pathlib import Path

from . import ansible_types as ans
from .helpers import ProjectPath, parse_file, FatalError, validate_ansible_object

class LoadError(Exception):
    """Raised when loading or validation failed."""

    #: The type of object that was being loaded.
    object_type: str
    #: Reason loading or validation failed.
    reason: str
    #: Relative path to the file that caused the error, if available.
    file_path: Path | None

    def __init__(self, object_type: str, reason: str, file_path: Path | None = None, extra_msg: str = '') -> None:
        if file_path:
            msg = f'Failed to load {object_type} at {file_path}: {reason}'
        else:
            msg = f'Failed to load {object_type}: {reason}'

        if extra_msg:
            msg = f'{msg}\n\n{extra_msg}'

        super().__init__(msg)
        self.object_type = object_type
        self.reason = reason
        self.file_path = file_path


def _type_to_str(type_: Any) -> str:
    if isinstance(type_, types.GenericAlias):
        return str(type_)
    return type_.__name__ if hasattr(type_, '__name__') else str(type_)  # type: ignore[no-any-return]


class LoadTypeError(LoadError):
    """Raised when loading led to a wrong type."""

    #: The expected type.
    expected_type: Any
    #: The actual type.
    actual_type: Type[Any]
    #: The actual object.
    actual_value: Any

    def __init__(self, object_type: str, expected_type: Any, actual_value: Any, file_path: Path | None = None) -> None:
        extra_msg = f'Expected {object_type} to be {_type_to_str(expected_type)}, got {_type_to_str(type(actual_value))} instead.\nActual value:\n{actual_value!r}'
        super().__init__(object_type, 'Wrong type encountered', file_path=file_path, extra_msg=extra_msg)
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
        raise LoadError('role metadata', 'Empty metadata', path.relative)
    if not isinstance(ds, dict):
        raise LoadTypeError('role metadata', dict, ds, path.relative)

    _validate_meta_galaxy_info(ds)
    _load_meta_platforms(ds)
    _load_meta_dependencies(ds)

    return ds, original_ds


def _validate_meta_galaxy_info(ds: dict[str, ans.AnsibleValue]) -> None:
    galaxy_info = ds.get('galaxy_info')
    if galaxy_info is None:
        ds['galaxy_info'] = ans.AnsibleMapping()
        return

    if not isinstance(galaxy_info, dict):
        raise LoadTypeError('role metadata galaxy_info', dict, galaxy_info)

_EXPECTED_PLATFORM_KEYS = {'name', 'versions'}

def _load_meta_platforms(ds: dict[str, ans.AnsibleValue]) -> None:
    assert isinstance(ds['galaxy_info'], dict)
    platforms = ds['galaxy_info'].get('platforms')
    if platforms is None:
        ds['galaxy_info']['platforms'] = ans.AnsibleSequence()
        return

    # Validation based on Ansible Galaxy loader
    # https://github.com/ansible/galaxy/blob/1fe0bd986aaeb4c45157d4e463b7049cad76a25e/galaxy/importer/loaders/role.py#L188
    # https://github.com/ansible/galaxy/blob/1fe0bd986aaeb4c45157d4e463b7049cad76a25e/galaxy/importer/loaders/role.py#L464
    if not isinstance(platforms, (tuple, list)):
        raise LoadTypeError('role metadata galaxy_info.platforms', list, platforms)

    validated_platforms = ans.AnsibleSequence()
    for platform in platforms:
        if not isinstance(platform, dict):
            print(f'Ignoring malformed platform {platform!r}: expected to be dict, got {_type_to_str(type(platform))}')
            continue

        name = platform.get('name')
        versions = platform.get('versions', ['all'])
        # https://github.com/ansible/galaxy/blob/1fe0bd986aaeb4c45157d4e463b7049cad76a25e/galaxy/importer/loaders/role.py#L471
        # ["any", "all"] is equivalent to ["all"]. Also, Ansible Galaxy doesn't
        # verify whether versions is actually a list, so if it's the string
        # "small", it'd still be considered ["all"].
        if 'all' in versions:
            versions = ['all']

        if not name:
            print(f'Ignoring malformed platform {platform!r}: missing "name" key')
            continue

        if not isinstance(versions, list):
            print(f'Ignoring malformed platform {platform!r}: "versions" expected to be list, got {_type_to_str(type(versions))}')
            continue

        validated_platforms.append(ans.AnsibleMapping({
            'name': str(name),  # type: ignore[dict-item]
            'versions': [str(v) for v in versions]  # type: ignore[dict-item]
        }))

    ds['galaxy_info']['platforms'] = validated_platforms


def _load_meta_dependencies(ds: dict[str, ans.AnsibleValue]) -> None:
    dependencies = ds.get('dependencies')
    if dependencies is None:
        ds['dependencies'] = ans.AnsibleSequence()
        return

    if not isinstance(dependencies, list):
        raise LoadTypeError('role dependencies', list, dependencies)

    new_deps = ans.AnsibleSequence()
    for dep in dependencies:
        if isinstance(dep, str):
            new_deps.append(ans.AnsibleMapping({ 'name': dep, 'when': ans.AnsibleSequence() }))
        elif isinstance(dep, dict):
            other_keys = dep.keys() - {'name', 'role', 'when'}
            if other_keys:
                raise LoadError('role metadata dependency', 'Superfluous properties in dependency', extra_msg=f'Found superfluous properties in {dep!r}: {", ".join(other_keys)}')

            if 'name' not in dep and 'role' not in dep:
                raise LoadError('role metadata dependency', 'Missing dependency name', extra_msg=f'"name" or "role" are required in dependencies')
            if 'name' in dep and (('name' in dep) == ('role' in dep)):
                raise LoadError('role metadata dependency', '"name" and "role" are mutually exclusive', extra_msg=f'Found both "role" and "name" in {dep!r}')
            elif 'role' in dep:
                dep['name'] = dep['role']
                del dep['role']

            if not isinstance(dep['name'], str):
                raise LoadTypeError('dependency name', str, dep['name'])

            when: ans.AnsibleBaseYAMLObject | None = dep.get('when')
            if when is None:
                dep['when'] = ans.AnsibleSequence()
            elif isinstance(when, str):
                dep['when'] = ans.AnsibleSequence([when])
            elif not isinstance(when, list) or not all(isinstance(cond, str) for cond in when):
                raise LoadTypeError('dependency condition', str | list[str], when)

            new_deps.append(dep)

        else:
            raise LoadTypeError('role dependency', str | dict, dep)

    ds['dependencies'] = new_deps


def load_variable_file(path: ProjectPath) -> tuple[dict[str, ans.AnsibleValue], Any]:
    original_ds = parse_file(path)
    ds = deepcopy(original_ds)

    if ds is None:
        ds = ans.AnsibleMapping()

    if not isinstance(ds, dict):
        raise LoadTypeError('variable file', dict, ds, path.relative)
    for var_name in ds:
        if not isinstance(var_name, str):
            raise LoadTypeError('variable name', str, var_name, path.relative)

    return ds, original_ds


def load_tasks_file(path: ProjectPath) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
    original_ds = parse_file(path)
    ds = deepcopy(original_ds)

    if ds is None:
        ds = ans.AnsibleSequence()

    if not isinstance(ds, list):
        raise LoadTypeError('task file', list, ds, path.relative)
    for content in ds:
        if not isinstance(content, dict) or not all(isinstance(prop, str) for prop in content):
            raise LoadTypeError('task file content', dict[str, Any], content, path.relative)

    return ds, original_ds


@contextmanager
def _patch_modargs_parser() -> Generator[None, None, None]:
    # Patch the ModuleArgsParser so that it doesn't verify whether the action exist.
    # Otherwise it'll complain on non-builtin actions
    old_mod_args_parse = ans.ModuleArgsParser.parse
    ans.ModuleArgsParser.parse = lambda self, skip_action_validation=False: old_mod_args_parse(self, skip_action_validation=True)  # type: ignore[assignment]

    try:
        yield
    finally:
        ans.ModuleArgsParser.parse = old_mod_args_parse  # type: ignore[assignment]


def _get_task_action(ds: dict[str, ans.AnsibleValue]) -> str:
    args_parser = ans.ModuleArgsParser(ds)
    (action, _, _) = args_parser.parse()
    return action


def _transform_task_static_include(ds: dict[str, ans.AnsibleValue]) -> None:
    # Current Ansible version crashes when the old static key is used.
    # Transform it to modern syntax, either into `import_tasks` if it's a
    # static include, or `include_tasks` if it isn't.
    if 'static' in ds:
        is_static = ans.convert_bool(ds['static'])

        include_args = ds['include']
        del ds['include']
        del ds['static']
        if is_static:
            ds['import_tasks'] = include_args
        else:
            ds['include_tasks'] = include_args


def _task_is_include_import_tasks(action: str) -> bool:
    return action in ans.C._ACTION_ALL_INCLUDE_IMPORT_TASKS

def _task_is_include(action: str) -> bool:
    return action in ans.C._ACTION_INCLUDE

def _task_is_import_playbook(action: str) -> bool:
    return action in ans.C._ACTION_IMPORT_PLAYBOOK

def _task_is_include_import_role(action: str) -> bool:
    return action in ans.C._ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES

@overload
def load_task(original_ds: dict[str, ans.AnsibleValue], as_handler: Literal[True]) -> tuple[ans.Handler, Any]: ...
@overload
def load_task(original_ds: dict[str, ans.AnsibleValue], as_handler: Literal[False]) -> tuple[ans.Task, Any]: ...
def load_task(original_ds: dict[str, ans.AnsibleValue], as_handler: bool) -> tuple[ans.Task | ans.Handler, Any]:
    ds = deepcopy(original_ds)

    with _patch_modargs_parser():
        action = _get_task_action(ds)
        is_include_tasks = _task_is_include_import_tasks(action)

        if _task_is_import_playbook(action):
            # This loader only gets called for tasks in task lists, so an
            # import_playbook is illegal here.
            raise LoadError('task', 'import_playbook is only allowed as a top-level playbook task')

        if _task_is_include(action):
            # Check for include/import tasks and transform them if the static
            # directive is present.
            _transform_task_static_include(ds)

        # This can happen and Ansible doesn't do anything about it, it just
        # ignores the when. Remove the directive so that defaults take over.
        if 'when' in ds and ds['when'] is None:
            del ds['when']

        # Use the correct Ansible representation so that more validation is done.
        ansible_cls: Type[ans.Task]
        if _task_is_include_import_role(action):
            ansible_cls = ans.IncludeRole
        elif not as_handler:
            ansible_cls = ans.Task if not is_include_tasks else ans.TaskInclude
        else:
            ansible_cls = ans.Handler if not is_include_tasks else ans.HandlerTaskInclude

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
_PatchedBlock.__name__ = 'Block'


def load_block(original_ds: dict[str, ans.AnsibleValue]) -> tuple[_PatchedBlock, Any]:
    ds = deepcopy(original_ds)

    if not _PatchedBlock.is_block(ds):
        raise LoadError('block', 'Not a block', extra_msg=f'Expected block to contain "block" keyword, but it does not.\n\n{ds!r}')

    raw_block = _PatchedBlock(ds)
    raw_block.load_data(ds)
    validate_ansible_object(raw_block)

    return raw_block, ds


class _PatchedPlay(ans.Play):

    tasks: list[dict[str, ans.AnsibleValue]]

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
_PatchedPlay.__name__ = 'Play'


def load_play(original_ds: dict[str, ans.AnsibleValue]) -> tuple[_PatchedPlay, Any]:
    ds = deepcopy(original_ds)

    raw_play = _PatchedPlay()
    raw_play.load_data(ds)
    validate_ansible_object(raw_play)

    return raw_play, original_ds


def load_playbook(path: ProjectPath) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
    original_ds = parse_file(path)
    ds = deepcopy(original_ds)

    if not ds:
        raise LoadError('playbook', 'Empty playbook', path.relative)
    if not isinstance(ds, list):
        raise LoadTypeError('playbook', list, ds, path.relative)

    return ds, original_ds
