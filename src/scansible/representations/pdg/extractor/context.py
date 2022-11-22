from __future__ import annotations

from typing import Generic, Generator, Literal, Mapping, Sequence, TypeVar, overload, cast

import json
from contextlib import contextmanager
from os.path import normpath
from pathlib import Path, PurePosixPath


from attrs import define
from loguru import logger

from scansible.representations import structural as struct_rep
from scansible.representations.structural.helpers import ProjectPath

from .. import representation as rep
from .var_context import VarContext

class IncludeContext:

    _playbook_base_path: ProjectPath | None
    _role_base_path: ProjectPath | None
    _last_included_file_path: ProjectPath | None

    def __init__(self, model: struct_rep.StructuralModel, *, lenient: bool) -> None:
        self._lenient = lenient

        if isinstance(model.root, struct_rep.Playbook):
            self._playbook_base_path = ProjectPath.from_root(model.path.parent)
            self._role_base_path = None
            self._last_included_file_path = self._playbook_base_path.join(model.path.name)
        else:
            self._playbook_base_path = None
            self._role_base_path = ProjectPath.from_root(model.path)
            if model.root.main_tasks_file is not None:
                self._last_included_file_path = self._role_base_path.join(model.root.main_tasks_file.file_path)

    @contextmanager
    def _enter_tasks_file(self, file_path: ProjectPath) -> Generator[None, None, None]:
        old_lifp = self._last_included_file_path
        self._last_included_file_path = file_path
        try:
            yield
        finally:
            self._last_included_file_path = old_lifp

    @contextmanager
    def _enter_role(self, role: struct_rep.Role, role_base_path: ProjectPath) -> Generator[None, None, None]:
        old_rbp = self._role_base_path
        self._role_base_path = role_base_path
        try:
            # TODO: this is ugly. we can probably use an ExitStack here.
            if role.main_tasks_file is not None:
                with self._enter_tasks_file(role_base_path.join(role.main_tasks_file.file_path)):
                    yield
            else:
                yield
        finally:
            self._role_base_path = old_rbp

    @contextmanager
    def load_and_enter_task_file(self, path: str) -> Generator[struct_rep.TaskFile | None, None, None]:
        real_path = self._find_file(path, 'tasks')
        if not real_path:
            yield None
            return

        struct_ctx = struct_rep.extractor.ExtractionContext(lenient=self._lenient)
        try:
            task_file = struct_rep.extractor.extract_tasks_file(real_path, struct_ctx)
        except Exception as e:
            logger.error(e)
            yield None
            return

        for bt in struct_ctx.broken_tasks:
            logger.error(bt.reason)

        with self._enter_tasks_file(real_path):
            yield task_file

    @contextmanager
    def load_and_enter_role(self, role_name: str) -> Generator[struct_rep.Role | None, None, None]:
        assert False, 'Not implemented yet'
        real_path: struct_rep.extractor.ProjectPath | None = None  # TODO!
        if not real_path:
            yield None
            return

        try:
            model = struct_rep.extractor.extract_role(real_path.absolute, role_name, 'UNKNOWN!', lenient=self._lenient)
        except Exception as e:
            logger.error(e)
            yield None
            return

        role = cast(struct_rep.Role, model.root)

        for bt in role.broken_tasks:
            logger.error(bt.reason)
        for bf in role.broken_files:
            logger.error(f'Could not extract {bf.path}: {bf.reason}')

        with self._enter_role(role, real_path):
            yield role

    def load_var_file(self, path: str) -> struct_rep.VariableFile | None:
        real_path = self._find_file(path, 'vars')
        if not real_path:
            return None

        try:
            return struct_rep.extractor.extract_variable_file(real_path)
        except Exception as e:
            logger.error(e)
            return None

    def _find_file(self, short_path: str, base_dir: str) -> struct_rep.extractor.ProjectPath | None:
        # Ansible's file resolution order:
        # <current role root>/{base_dir}/{path}
        # <current role root>/{path}
        # <current task file dir>/{base_dir}/{path}
        # <current task file dir>/{path}
        # <playbook dir>/{base_dir}/{path}
        # <playbook dir>/{path}
        #
        # We should also take care not to allow for path traversal outside of
        # controlled project directories through relative paths.
        base_file_path = Path(short_path).expanduser()
        if base_file_path.is_absolute():
            logger.error(f'Cannot handle absolute paths: {short_path}')
            return None

        base_search_dirs = []
        if self._role_base_path is not None:
            base_search_dirs.extend([
                self._role_base_path.join(base_dir),
                self._role_base_path
            ])

        assert self._last_included_file_path is not None, 'Someone forgot to initialise the includes'
        lifp_pp = ProjectPath(self._last_included_file_path.root, self._last_included_file_path.absolute.parent)
        base_search_dirs.extend([
            lifp_pp.join(base_dir),
            lifp_pp
        ])

        if self._playbook_base_path is not None:
            base_search_dirs.extend([
                self._playbook_base_path.join(base_dir),
                self._playbook_base_path
            ])

        for search_path in base_search_dirs:
            logger.debug(f'Checking whether {short_path} exists in {search_path}')
            if not self._is_in_project(search_path.absolute / short_path):
                logger.warning(f'Blocked attempted path traversal on {search_path.absolute / short_path}')
                continue

            found_path = struct_rep.extractor.find_file(search_path, short_path)
            if found_path is not None:
                logger.debug(f'Found file: {found_path}')
                return found_path

        return None

    def _is_in_project(self, path: Path) -> bool:
        # normalize path: resolve .. to parent and . to self, etc.
        path = Path(normpath(path))
        return ((self._role_base_path is not None and path.is_relative_to(self._role_base_path.absolute))
            or (self._playbook_base_path is not None and path.is_relative_to(self._playbook_base_path.absolute)))


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
    graph: rep.Graph
    include_ctx: IncludeContext
    model_root: struct_rep.Role | struct_rep.Playbook
    # Auxiliary information about variable visibility. We don't store this in
    # the graph itself but in a companion file.
    visibility_information: VisibilityInformation
    _next_iv_id: int

    def __init__(self, graph: rep.Graph, model: struct_rep.StructuralModel, *, lenient: bool) -> None:
        self.vars = VarContext(self)
        self.graph = graph
        self.model_root = model.root
        self.include_ctx = IncludeContext(model, lenient=lenient)
        self.visibility_information = VisibilityInformation()
        self._next_iv_id = 0

    def next_iv_id(self) -> int:
        self._next_iv_id += 1
        return self._next_iv_id - 1


@define
class ExtractionResult:
    added_control_nodes: list[rep.ControlNode]
    added_variable_nodes: list[rep.Variable]


@define
class TaskExtractionResult(ExtractionResult):
    next_predecessors: list[rep.ControlNode]
