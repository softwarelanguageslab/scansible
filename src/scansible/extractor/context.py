from __future__ import annotations

from typing import Generator, Literal, Sequence, TypeVar, overload

import json
from contextlib import contextmanager
from pathlib import Path, PurePosixPath

from loguru import logger
from pydantic import BaseModel

from voyager.models.structural.role import (
        HandlerFile, DefaultVarFile, RoleVarFile, TaskFile, Role)
from voyager.models.structural.abstract import ContainerFile
from voyager.models.structural.base import BaseFile

from ..models.graph import Graph
from ..models import nodes as n
from .var_context import VarContext

_FileType = TypeVar('_FileType', bound=BaseFile)

def get_stem(file_name: str) -> str:
    return PurePosixPath(file_name).stem

def _find_file_in_list(file_list: Sequence[_FileType], file_name: str, ignore_ext: bool = False) -> _FileType | None:
    for f in file_list:
        if (f.file_name == file_name
            or (ignore_ext and get_stem(f.file_name) == get_stem(file_name))):
            return f
    return None

class Files:
    role: Role

    def __init__(self, role: Role, role_path: Path) -> None:
        self.role = role
        self._root_dir = role_path
        self._fake_root_dir = Path('/role')
        self._include_stack: list[Path] = []

    @contextmanager
    def enter_included_file(self, file: TaskFile) -> Generator[None, None, None]:
        self._include_stack.append(self._fake_root_dir / file.file_name)
        yield
        self._include_stack.pop()

    @property
    def main_task_file(self) -> TaskFile | None:
        return _find_file_in_list(self.role.task_files, 'tasks/main', ignore_ext=True)

    @property
    def main_handler_file(self) -> HandlerFile | None:
        return _find_file_in_list(self.role.handler_files, 'handlers/main', ignore_ext=True)

    @property
    def main_var_file(self) -> RoleVarFile | None:
        return _find_file_in_list(self.role.role_var_files, 'vars/main', ignore_ext=True)

    @property
    def main_defaults_file(self) -> DefaultVarFile | None:
        return _find_file_in_list(self.role.default_var_files, 'defaults/main', ignore_ext=True)

    def _load_file(self, path: Path, desired_type: str) -> RoleVarFile | TaskFile | None:
        if not path.is_relative_to(self._fake_root_dir):
            # Path traversal going outside of role, don't follow it.
            logger.debug(f'Search path not relative to role: {path}')
            return None
        rel_path = path.relative_to(self._fake_root_dir)
        base_dir = rel_path.parts[0]
        if base_dir == desired_type:
            # In the expected directory, should have already been parsed correctly.
            file_list: Sequence[RoleVarFile | TaskFile]
            if desired_type == 'tasks':
                file_list = self.role.task_files
            else:
                file_list = self.role.role_var_files
            found_file = _find_file_in_list(file_list, str(rel_path))
            if found_file is None:
                logger.debug(f'Could not find already parsed {rel_path}')
            else:
                return found_file

        # File isn't in the "right" directory, so we'll need to parse it. It
        # may not have been parsed previously because the directory was never
        # considered, or parsing it may have been attempted but because it's a
        # different file type, may have failed
        if not (self._root_dir / rel_path).is_file():
            logger.debug(f'{rel_path} does not exist')
            return None
        try:
            if desired_type == 'tasks':
                return Role.load_extra_tasks(self._root_dir, rel_path)
            else:
                return Role.load_extra_vars(self._root_dir, rel_path)
        except Exception as e:
            logger.error(e)
            return None

    @overload
    def _find_file(self, file_path: str, base_dir: Literal['tasks']) -> TaskFile | None:
        ...
    @overload
    def _find_file(self, file_path: str, base_dir: Literal['vars']) -> RoleVarFile | None:
        ...
    def _find_file(self, file_path: str, base_dir: Literal['tasks', 'vars']) -> RoleVarFile | TaskFile | None:
        # Ansible's file resolution order:
        # <role root>/{base_dir}/{path}
        # <role root>/{path}
        # <current task file dir>/{base_dir}/{path}
        # <current task file dir>/{path}
        # <playbook dir>/{base_dir}/{path}
        # <playbook dir>/{path}
        #
        # We don't have a playbook, so we don't search the last two options.
        # We should also take care not to allow for path traversal outside of
        # the role root through relative paths.
        base_file_path = Path(file_path).expanduser()
        if base_file_path.is_absolute():
            logger.error(f'Cannot handle absolute paths: {file_path}')
            return None

        base_search_dirs = [
            self._fake_root_dir / base_dir,
            self._fake_root_dir,
            self._include_stack[-1].parent / base_dir,
            self._include_stack[-1].parent]

        search_paths = [(search_dir / file_path).resolve() for search_dir in base_search_dirs]
        for search_path in search_paths:
            logger.debug(f'Trying to load {search_path}')
            loaded_file = self._load_file(search_path, base_dir)
            if loaded_file is not None:
                logger.debug('Found file')
                return loaded_file

        return None

    def find_task_file(self, path: str) -> TaskFile | None:
        return self._find_file(path, 'tasks')

    def find_var_file(self, path: str) -> RoleVarFile | None:
        return self._find_file(path, 'vars')


class VisibilityInformation:
    def __init__(self) -> None:
        self._store: dict[tuple[str, int], set[tuple[str, int]]] = dict()

    def set_info(self, var_name: str, def_version: int, visible_definitions: set[tuple[str, int]]) -> None:
        assert (var_name, def_version) not in self._store, f'Internal Error: Visibility information already set for {var_name}@{def_version}'
        self._store[(var_name, def_version)] = visible_definitions

    def get_info(self, var_name: str, def_version: int) -> set[tuple[str, int]]:
        assert (var_name, def_version) in self._store, f'Internal Error: Visibility information not stored for {var_name}@{def_version}'
        return self._store[(var_name, def_version)]

    def dump(self) -> str:
        """Dump to JSON."""
        as_lists = [[list(k), [list(v) for v in vals]] for k, vals in self._store.items()]
        return json.dumps(as_lists)

    @classmethod
    def load(self, payload: str) -> VisibilityInformation:
        inst = VisibilityInformation()
        as_lists = json.loads(payload)
        for k, vals in as_lists:
            name, rev = k
            vals_as_tuples = {(vname, vrev) for vname, vrev in vals}
            inst.set_info(name, rev, vals_as_tuples)
        return inst


class ExtractionContext:
    vars: VarContext
    graph: Graph
    files: Files
    role: Role
    play: Play | None
    # Auxiliary information about variable visibility. We don't store this in
    # the graph itself but in a companion file.
    visibility_information: VisibilityInformation
    _next_id: int
    _next_iv_id: int

    def __init__(self, graph: Graph, role: Role, role_path: Path, is_pb: bool) -> None:
        self.vars = VarContext(self)
        self.graph = graph
        self.role = role
        self.is_pb = is_pb
        self.files = Files(role, role_path)
        self.visibility_information = VisibilityInformation()
        self._next_id = 0
        self._next_iv_id = 0

    def next_id(self) -> int:
        self._next_id += 1
        return self._next_id - 1

    def next_iv_id(self) -> int:
        self._next_iv_id += 1
        return self._next_iv_id - 1


def get_file_name(f: ContainerFile | str) -> str:  # type: ignore[type-arg]
    if not isinstance(f, str):
        return get_file_name(f.file_name)
    parent_dir, *name_no_dir_parts = f.split('/')
    if name_no_dir_parts and parent_dir in ('tasks', 'handlers', 'vars', 'defaults'):
        name_no_dir = '/'.join(name_no_dir_parts)
    else:
        name_no_dir = f

    name_no_ext = '.'.join(name_no_dir.split('.')[:-1])
    return name_no_ext

class ExtractionResult(BaseModel):
    added_control_nodes: list[n.ControlNode]
    added_variable_nodes: list[n.Variable]

class TaskExtractionResult(ExtractionResult):
    next_predecessors: list[n.ControlNode]
