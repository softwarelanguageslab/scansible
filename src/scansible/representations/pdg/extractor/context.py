from __future__ import annotations

from typing import Generator, Sequence, TypeAlias, cast

import json
import re
import textwrap
from collections import defaultdict
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from os.path import normpath
from pathlib import Path

from loguru import logger

from scansible.representations import structural as struct_rep
from scansible.representations.structural.helpers import (
    ProjectPath,
    capture_output,
    find_all_files,
    find_file,
    prevent_undesired_operations,
)
from scansible.utils import join_sequences

from .. import representation as rep
from .expressions import VarContext

LocTuple: TypeAlias = tuple[str, int, int]


class IncludeContext:
    _playbook_base_path: ProjectPath | None

    _include_stack: list[tuple[ProjectPath | None, rep.NodeLocation | None]]
    _role_stack: list[ProjectPath]

    @property
    def _role_base_path(self) -> ProjectPath | None:
        return self._role_stack[-1] if self._role_stack else None

    @property
    def _last_included_file_path(self) -> ProjectPath | None:
        return self._include_stack[-1][0]

    @property
    def last_include_location(self) -> rep.NodeLocation | None:
        return self._include_stack[-1][1]

    def __init__(
        self,
        model: struct_rep.StructuralModel,
        role_search_paths: Sequence[Path],
        *,
        lenient: bool,
    ) -> None:
        self.lenient = lenient
        self._role_search_paths = role_search_paths
        self._role_stack = []
        self._include_stack = []

        _last_included_file_path = None
        if isinstance(model.root, struct_rep.Playbook):
            self._playbook_base_path = ProjectPath.from_root(model.path.parent)
            _last_included_file_path = self._playbook_base_path.join(model.path.name)
        else:
            self._playbook_base_path = None
            role_base_path = ProjectPath.from_root(model.path)
            self._role_stack.append(role_base_path)
            if model.root.main_tasks_file is not None:
                _last_included_file_path = role_base_path.join(
                    model.root.main_tasks_file.file_path
                )

        self.all_included_files: set[Path] = set()
        self._include_stack.append((_last_included_file_path, None))
        if self._last_included_file_path is not None:
            self.all_included_files.add(self._last_included_file_path.absolute)

    @contextmanager
    def _enter_file(
        self, file_path: ProjectPath, includer_location: rep.NodeLocation | None
    ) -> Generator[None, None, None]:
        if includer_location is None:
            assert self.last_include_location is None

        self._include_stack.append((file_path, includer_location))
        self.all_included_files.add(file_path.absolute)
        try:
            yield
        finally:
            self._include_stack.pop()

    @contextmanager
    def _enter_role(
        self,
        role: struct_rep.Role,
        role_base_path: ProjectPath,
        includer_location: rep.NodeLocation,
    ) -> Generator[None, None, None]:
        self._role_stack.append(role_base_path)
        try:
            # TODO: this is ugly. we can probably use an ExitStack here.
            if role.main_tasks_file is not None:
                with self._enter_file(
                    role_base_path.join(role.main_tasks_file.file_path),
                    includer_location,
                ):
                    yield
            else:
                yield
        finally:
            self._role_stack.pop()

    @contextmanager
    def load_and_enter_task_file(
        self, path: str, includer_location: rep.NodeLocation
    ) -> Generator[struct_rep.TaskFile | None, None, None]:
        real_path = self._find_file(path, "tasks")
        if not real_path:
            yield None
            return

        if any(
            prev_path is not None and prev_path.absolute == real_path.absolute
            for prev_path, _ in self._include_stack
        ):
            logger.warning(f"Refusing to enter {real_path}: Recursive include")
            yield None
            return

        struct_ctx = struct_rep.extractor.ExtractionContext(lenient=self.lenient)
        try:
            with capture_output() as output, prevent_undesired_operations():
                task_file = struct_rep.extractor.extract_tasks_file(
                    real_path, struct_ctx
                )
            if logged_output := output.getvalue():
                logger.warning(logged_output)
        except Exception as e:
            logger.error(e)
            yield None
            return

        for bt in struct_ctx.broken_tasks:
            logger.error(bt.reason)

        with self._enter_file(real_path, includer_location):
            yield task_file

    @contextmanager
    def load_and_enter_role(
        self, role_name: str, includer_location: rep.NodeLocation
    ) -> Generator[struct_rep.Role | None, None, None]:
        real_path = self.find_role(role_name)
        if not real_path:
            yield None
            return

        if any(
            prev_path.absolute == real_path.absolute for prev_path in self._role_stack
        ):
            logger.warning(f"Refusing to enter {real_path}: Recursive include")
            yield None
            return

        try:
            model = struct_rep.extractor.extract_role(
                real_path.absolute, role_name, "UNKNOWN!", lenient=self.lenient
            )
        except Exception as e:
            logger.error(e)
            yield None
            return

        role = cast(struct_rep.Role, model.root)

        for bt in role.broken_tasks:
            logger.error(bt.reason)
        for bf in role.broken_files:
            logger.error(f"Could not extract {bf.path}: {bf.reason}")

        with self._enter_role(role, real_path, includer_location):
            yield role

    @contextmanager
    def enter_role_file(self, role_file_path: Path) -> Generator[None, None, None]:
        assert self._role_base_path is not None, (
            "Should not attempt to enter role file without having entered role"
        )
        with self._enter_file(
            self._role_base_path.join(role_file_path), self.last_include_location
        ):
            yield

    @contextmanager
    def load_and_enter_var_file(
        self, path: str, includer_location: rep.NodeLocation
    ) -> Generator[struct_rep.VariableFile | None, None, None]:
        real_path = self._find_file(path, "vars")
        if not real_path:
            yield None
            return

        try:
            with capture_output() as output, prevent_undesired_operations():
                var_file = struct_rep.extractor.extract_variable_file(real_path)
            if logged_output := output.getvalue():
                logger.warning(logged_output)
        except Exception as e:
            logger.error(e)
            yield None
            return

        with self._enter_file(real_path, includer_location):
            yield var_file

    def find_matching_roles(self, name_pattern: str) -> set[str]:
        pattern = re.compile(name_pattern + "$")

        def walk_dir(path: Path, root_path: Path) -> Iterable[str]:
            for child in path.iterdir():
                if not child.is_dir():
                    continue
                role_name = str(path.relative_to(root_path))
                if pattern.match(role_name):
                    yield role_name
                else:
                    yield from walk_dir(child, root_path)

        results: set[str] = set()
        for search_dir in self._get_role_search_dirs():
            if not search_dir.is_dir():
                continue
            results |= set(walk_dir(search_dir, search_dir))

        return results

    def find_matching_task_files(self, name_pattern: str) -> set[str]:
        return self._find_matching_files(name_pattern, "tasks")

    def find_matching_var_files(self, name_pattern: str) -> set[str]:
        return self._find_matching_files(name_pattern, "vars")

    def _find_matching_files(self, name_pattern: str, base_dir: str) -> set[str]:
        def _insert_extension(p: str) -> str:
            if p.endswith(("\\.yml", "\\.yaml")):
                return p
            return p + "(\\.yml|\\.yaml)?"

        pattern = re.compile(_insert_extension(name_pattern) + "$")

        # Use a set so that paths get deduplicated. Paths are relative to the
        # search dir, such that when we attempt to include it, we'll always take
        # the higher precedence one.
        results: set[str] = set()
        for search_dir in self._get_file_search_dirs(base_dir):
            if not search_dir.absolute.is_dir():
                continue
            files = [
                str(f.absolute.relative_to(search_dir.absolute))
                for f in find_all_files(search_dir)
            ]

            results |= set(f for f in files if pattern.match(f))

        return results

    def find_task_file(self, name: str) -> ProjectPath | None:
        return self._find_file(name, "tasks")

    def find_var_file(self, name: str) -> ProjectPath | None:
        return self._find_file(name, "vars")

    def _find_file(self, short_path: str, base_dir: str) -> ProjectPath | None:
        # We should take care not to allow for path traversal outside of
        # controlled project directories through relative paths.
        base_file_path = Path(short_path).expanduser()
        if base_file_path.is_absolute():
            logger.error(f"Cannot handle absolute paths: {short_path}")
            return None

        base_search_dirs = self._get_file_search_dirs(base_dir)

        for search_path in base_search_dirs:
            logger.debug(f"Checking whether {short_path} exists in {search_path}")
            if not self._is_in_project(search_path.absolute / short_path):
                logger.warning(
                    f"Blocked attempted path traversal on {search_path.absolute / short_path}"
                )
                continue

            found_path = find_file(search_path, short_path)
            if found_path is not None:
                logger.debug(f"Found file: {found_path}")
                return found_path

        return None

    def _get_file_search_dirs(self, base_dir: str) -> Iterable[ProjectPath]:
        # Ansible's file resolution order:
        # <current role root>/{base_dir}/{path}
        # <current role root>/{path}
        # <current task file dir>/{base_dir}/{path}
        # <current task file dir>/{path}
        # <playbook dir>/{base_dir}/{path}
        # <playbook dir>/{path}
        if self._role_base_path is not None:
            yield self._role_base_path.join(base_dir)
            yield self._role_base_path

        assert self._last_included_file_path is not None, (
            "Someone forgot to initialise the includes"
        )
        lifp_pp = ProjectPath(
            self._last_included_file_path.root,
            self._last_included_file_path.absolute.parent,
        )
        yield lifp_pp.join(base_dir)
        yield lifp_pp

        if self._playbook_base_path is not None:
            yield self._playbook_base_path.join(base_dir)
            yield self._playbook_base_path

    def find_role(self, role_name: str) -> ProjectPath | None:
        base_search_dirs = self._get_role_search_dirs()

        for search_path in base_search_dirs:
            logger.debug(f"Checking whether role {role_name} exists in {search_path}")
            candidate_path = Path(normpath(search_path / role_name))
            if not candidate_path.is_relative_to(search_path):
                logger.warning(f"Blocked attempted path traversal on {candidate_path}")
                continue
            candidate_path = candidate_path.resolve()

            if candidate_path.is_dir():
                logger.debug(f"Found role: {candidate_path}")
                # TODO: Are we sure we want to create a new root path here?
                return ProjectPath.from_root(candidate_path)

        return None

    def _get_role_search_dirs(self) -> Iterable[Path]:
        # Ansible's role resolution order:
        # - collections (skipped)
        # - <playbook dir>/roles/{name}
        # - <default role dir>/{name}
        # - <current role's parent dir>/{name}
        # - <playbook dir>/{name}
        if self._playbook_base_path is not None:
            yield self._playbook_base_path.join("roles").absolute

        yield from self._role_search_paths

        if self._role_base_path is not None:
            yield self._role_base_path.absolute

        if self._playbook_base_path is not None:
            yield self._playbook_base_path.absolute

    def _is_in_project(self, path: Path) -> bool:
        # normalize path: resolve .. to parent and . to self, etc.
        path = Path(normpath(path))
        return (
            self._role_base_path is not None
            and path.is_relative_to(self._role_base_path.absolute)
        ) or (
            self._playbook_base_path is not None
            and path.is_relative_to(self._playbook_base_path.absolute)
        )


class VisibilityInformation:
    def __init__(self) -> None:
        self._store: dict[tuple[str, int], set[tuple[str, int]]] = dict()

    def set_info(
        self, var_name: str, def_version: int, visible_definitions: set[tuple[str, int]]
    ) -> None:
        assert (
            var_name,
            def_version,
        ) not in self._store, (
            f"Internal Error: Visibility information already set for {var_name}@{def_version}"
        )
        self._store[(var_name, def_version)] = visible_definitions

    def get_info(self, var_name: str, def_version: int) -> set[tuple[str, int]]:
        assert (
            var_name,
            def_version,
        ) in self._store, (
            f"Internal Error: Visibility information not stored for {var_name}@{def_version}"
        )
        return self._store[(var_name, def_version)]

    def dump(self) -> str:
        """Dump to JSON."""
        as_lists = [
            [list(k), [list(v) for v in vals]] for k, vals in self._store.items()
        ]
        return json.dumps(as_lists)

    @classmethod
    def load(cls, payload: str) -> VisibilityInformation:
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
    errors: list[tuple[str, LocTuple | None]]
    _next_iv_id: int

    handler_notifications: dict[str, set[rep.Task]]
    active_conditions: Sequence[rep.DataNode]
    active_loops: Sequence[rep.DataNode]

    def __init__(
        self,
        graph: rep.Graph,
        model: struct_rep.StructuralModel,
        role_search_paths: Sequence[Path],
        *,
        lenient: bool,
    ) -> None:
        self.vars = VarContext(self)
        self.graph = graph
        self.model_root = model.root
        self.include_ctx = IncludeContext(model, role_search_paths, lenient=lenient)
        self.visibility_information = VisibilityInformation()
        self._next_iv_id = 0
        self.errors = []
        self.handler_notifications = defaultdict(set)
        self.active_conditions = []
        self.active_loops = []

    @contextmanager
    def activate_conditions(self, conditions: list[rep.DataNode]) -> Iterator[None]:
        old_conditions = self.active_conditions
        self.active_conditions = join_sequences(old_conditions, conditions)
        try:
            yield
        finally:
            self.active_conditions = old_conditions

    @contextmanager
    def activate_loop(self, loop_data_node: rep.DataNode) -> Iterator[None]:
        old_loops = self.active_loops
        self.active_loops = join_sequences(old_loops, [loop_data_node])
        try:
            yield
        finally:
            self.active_loops = old_loops

    def next_iv_id(self) -> int:
        self._next_iv_id += 1
        return self._next_iv_id - 1

    def get_location(self, ds: object) -> rep.NodeLocation:
        file: str
        line: int
        column: int

        if hasattr(ds, "ansible_pos"):
            file, line, column = ds.ansible_pos  # type: ignore[attr-defined]
        elif hasattr(ds, "location"):
            file, line, column = ds.location  # type: ignore[attr-defined]
        else:
            file, line, column = "unknown file", -1, -1

        return rep.NodeLocation(
            file=file,
            line=line,
            column=column,
            includer_location=self.include_ctx.last_include_location,
        )

    def record_extraction_error(self, reason: str, location: LocTuple | None) -> None:
        self.errors.append((reason, location))

    def summarise_extraction_errors(self) -> str:
        reason_to_location: dict[str, list[LocTuple | None]] = defaultdict(list)
        for reason, location in self.errors:
            reason_to_location[reason.strip()].append(location)

        parts: list[str] = []
        for reason, locations in sorted(reason_to_location.items()):
            num_unknown = len([loc for loc in locations if loc is None])
            loc_strs = sorted(
                set(":".join(map(str, loc)) for loc in locations if loc is not None)
            )
            if num_unknown:
                prefix = "and " if loc_strs else ""
                loc_strs.append(f"{prefix}{num_unknown} unknown location(s)")
            locs = textwrap.indent("\n".join(loc_strs), " " * 4)
            parts.append(f"{reason}\n{locs}")

        return "\n\n".join(parts)

    @property
    def file_set(self) -> frozenset[Path]:
        return frozenset(self.include_ctx.all_included_files)
