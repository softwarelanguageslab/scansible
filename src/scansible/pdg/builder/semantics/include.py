"""Management of file inclusion."""

from __future__ import annotations

from typing import cast, final

import re
from collections.abc import Generator, Iterable, Sequence
from contextlib import contextmanager
from os.path import normpath
from pathlib import Path

from loguru import logger
from pydantic import ValidationError
from ruamel.yaml import YAMLError

from scansible import ast
from scansible.utils import ProjectPath, capture_output, find_all_files, find_file

from ... import representation as rep


@final
class InclusionManager:
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
        self, model: ast.AST, role_search_paths: Sequence[Path], *, lenient: bool
    ) -> None:
        self.lenient = lenient
        self._role_search_paths = role_search_paths
        self._role_stack = []
        self._include_stack = []

        _last_included_file_path = None
        if isinstance(model.root, ast.Playbook):
            self._playbook_base_path = ProjectPath.from_root(model.path.parent)
            _last_included_file_path = self._playbook_base_path.join(model.path.name)
        else:
            self._playbook_base_path = None
            role_base_path = ProjectPath.from_root(model.path)
            self._role_stack.append(role_base_path)
            if model.root.main_tasks_file is not None:
                _last_included_file_path = role_base_path.join(
                    model.root.main_tasks_file.path
                )

        self.all_included_files: set[Path] = set()
        self._include_stack.append((_last_included_file_path, None))
        if self._last_included_file_path is not None:
            self.all_included_files.add(self._last_included_file_path.absolute)

    @contextmanager
    def _enter_file(
        self, file_path: ProjectPath, includer_location: rep.NodeLocation | None
    ) -> Generator[None]:
        if includer_location is None:
            assert self.last_include_location is None

        self._include_stack.append((file_path, includer_location))
        self.all_included_files.add(file_path.absolute)
        try:
            yield
        finally:
            _ = self._include_stack.pop()

    @contextmanager
    def _enter_role(
        self,
        role: ast.Role,
        role_base_path: ProjectPath,
        includer_location: rep.NodeLocation,
    ) -> Generator[None]:
        self._role_stack.append(role_base_path)
        try:
            # TODO: this is ugly. we can probably use an ExitStack here.
            if role.main_tasks_file is not None:
                with self._enter_file(
                    role_base_path.join(role.main_tasks_file.path), includer_location
                ):
                    yield
            else:
                yield
        finally:
            _ = self._role_stack.pop()

    @contextmanager
    def load_and_enter_task_file(
        self, path: str, includer_location: rep.NodeLocation
    ) -> Generator[ast.TaskFile | None]:
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

        struct_ctx = ast.ExtractionContext(lenient=self.lenient)
        try:
            with capture_output() as output:
                task_file = ast.TaskFile.load(real_path, struct_ctx)
            if logged_output := output.getvalue():
                logger.warning(logged_output)
        except (ValidationError, YAMLError) as e:
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
    ) -> Generator[ast.Role | None]:
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
            model = ast.extract_role(real_path.absolute, lenient=self.lenient)
        except (ValidationError, YAMLError) as e:
            logger.error(e)
            yield None
            return

        for bt in model.broken_tasks:
            logger.error(bt.reason)
        for bf in model.broken_files:
            logger.error(f"Could not extract AST for {bf.path}: {bf.reason}")

        role = cast(ast.Role, model.root)
        with self._enter_role(role, real_path, includer_location):
            yield role

    @contextmanager
    def enter_role_file(self, role_file_path: Path) -> Generator[None]:
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
    ) -> Generator[ast.VariableFile | None]:
        real_path = self._find_file(path, "vars")
        if not real_path:
            yield None
            return

        try:
            with capture_output() as output:
                var_file = ast.VariableFile.load(
                    real_path, ast.ExtractionContext(lenient=self.lenient)
                )
            if logged_output := output.getvalue():
                logger.warning(logged_output)
        except (ValidationError, YAMLError) as e:
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

            results |= {f for f in files if pattern.match(f)}

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
            logger.trace(f"Checking whether {short_path} exists in {search_path}")
            if not self._is_in_project(search_path.absolute / short_path):
                logger.warning(
                    f"Blocked attempted path traversal on {search_path.absolute / short_path}"
                )
                continue

            found_path = find_file(search_path, short_path)
            if found_path is not None:
                logger.trace(f"Found file: {found_path}")
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
            logger.trace(f"Checking whether role {role_name} exists in {search_path}")
            candidate_path = Path(normpath(search_path / role_name))
            if not candidate_path.is_relative_to(search_path):
                logger.warning(f"Blocked attempted path traversal on {candidate_path}")
                continue
            candidate_path = candidate_path.resolve()

            if candidate_path.is_dir():
                logger.trace(f"Found role: {candidate_path}")
                # TODO: Are we sure we want to create a new root path here?
                return ProjectPath.from_root(candidate_path)

        return None

    def _get_role_search_dirs(self) -> Iterable[Path]:
        # Ansible's role resolution order:
        # 1. collections (skipped)
        # 2. <playbook dir>/roles/{name}
        # 3. <default role dir>/{name}
        # 4. <current role's parent dir>/{name}
        # 5. <playbook dir>/{name}
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
