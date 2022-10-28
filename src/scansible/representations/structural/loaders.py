"""Loaders for Ansible objects.

The loaders generally return a tuple of two values: The loaded, validated and
transformed data structure (possibly as an Ansible object), and the original
parsed data structure without modifications.
"""

from __future__ import annotations

from typing import Any, Type

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
    _validate_meta_platforms(ds)
    _validate_meta_dependencies(ds)

    return ds, original_ds


def _validate_meta_galaxy_info(ds: dict[str, ans.AnsibleValue]) -> None:
    galaxy_info = ds.get('galaxy_info')
    if galaxy_info is None:
        ds['galaxy_info'] = ans.AnsibleMapping()
        return

    if not isinstance(galaxy_info, dict):
        raise LoadTypeError('role metadata galaxy_info', dict, galaxy_info)

_EXPECTED_PLATFORM_KEYS = {'name', 'versions'}

def _validate_meta_platforms(ds: dict[str, ans.AnsibleValue]) -> None:
    assert isinstance(ds['galaxy_info'], dict)
    platforms = ds['galaxy_info'].get('platforms')
    if platforms is None:
        ds['galaxy_info']['platforms'] = ans.AnsibleSequence()
        return

    if not isinstance(platforms, (tuple, list)):
        raise LoadTypeError('role metadata galaxy_info.platforms', list, platforms)

    for platform in platforms:
        if not isinstance(platform, dict):
            raise LoadTypeError('role metadata platform', dict, platform)

        for key in _EXPECTED_PLATFORM_KEYS:
            if key not in platform:
                raise LoadError('role metadata platform', f'Missing property "{key}"')
        other_keys = platform.keys() - _EXPECTED_PLATFORM_KEYS
        if other_keys:
            raise LoadError('role metadata platforms', 'Superfluous properties in platform', extra_msg=f'Found superfluous properties in {platform!r}: {", ".join(other_keys)}')

        if not isinstance(platform['name'], str):
            raise LoadTypeError('platform name', str, platform['name'])
        if not isinstance(platform['versions'], list) or not all(isinstance(version, (str, int, float)) for version in platform['versions']):
            raise LoadTypeError('platform versions', list[str | int | float], platform['versions'])


def _validate_meta_dependencies(ds: dict[str, ans.AnsibleValue]) -> None:
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
            raise LoadTypeError('variable', str, var_name, path.relative)

    return ds, original_ds
