"""AST nodes for roles."""

from __future__ import annotations

from typing import Callable, override

from collections.abc import Sequence
from functools import cached_property

from pydantic import ValidationError

from scansible.utils import ProjectPath, SourceFileMap, find_all_files, find_file

from ..common import BrokenFile, ExtractionContext
from .base import ASTFile
from .role_meta import MetaFile
from .task import HandlerFile, TaskFile
from .variable import VariableFile

#: Signature of a function that loads an `ASTFile` from a project path.
type Extractor[T] = Callable[[ProjectPath, ExtractionContext], T]


def _safe_extract[T: ASTFile](
    extractor: Extractor[T], file_path: ProjectPath, ctx: ExtractionContext
) -> T | None:
    """Run `extractor`, recording a `BrokenFile` and returning `None` on validation failure instead of raising."""
    try:
        return extractor(file_path, ctx)
    except ValidationError as e:
        ctx.broken_files.append(BrokenFile(path=file_path.relative, reason=str(e)))


def _safe_extract_all[T: ASTFile](
    extractor: Extractor[T], file_paths: Sequence[ProjectPath], ctx: ExtractionContext
) -> Sequence[tuple[str, T]]:
    """Run `_safe_extract` over multiple paths, returning only the successes, keyed by path."""
    results: list[T] = []
    for file_path in file_paths:
        if (result := _safe_extract(extractor, file_path, ctx)) is not None:
            results.append(result)
    return [(str(file.path), file) for file in results]


# Need arbitrary_types_allowed=True to put SourceFileMap into the model.
class Role(ASTFile, frozen=True, arbitrary_types_allowed=True):
    """Represents an Ansible role, assembling its constituent files into a single tree."""

    #: Role's main metadata file.
    meta_file: MetaFile | None
    #: Role's variable files in the defaults/* subdirectory, indexed by file name
    #: without directory prefix.
    default_var_files: SourceFileMap[VariableFile]
    #: Role's variable files in the vars/* subdirectory, indexed by file name
    #: without directory prefix.
    role_var_files: SourceFileMap[VariableFile]
    #: Role's task files in the tasks/* subdirectory, indexed by file name
    #: without directory prefix.
    task_files: SourceFileMap[TaskFile]
    #: Role's task files in the handlers/* subdirectory, indexed by file name
    #: without directory prefix.
    handler_files: SourceFileMap[HandlerFile]

    @cached_property
    def main_defaults_file(self) -> VariableFile | None:
        """The defaults/main.yml file."""
        return self.default_var_files.get("main")

    @cached_property
    def main_vars_file(self) -> VariableFile | None:
        """The vars/main.yml file."""
        return self.role_var_files.get("main")

    @cached_property
    def main_tasks_file(self) -> TaskFile | None:
        """The tasks/main.yml file."""
        return self.task_files.get("main")

    @cached_property
    def main_handlers_file(self) -> HandlerFile | None:
        """The handlers/main.yml file."""
        return self.handler_files.get("main")

    @classmethod
    @override
    def load(
        cls, path: ProjectPath, context: ExtractionContext, extract_all: bool = False
    ) -> Role:
        """Load and parse a role from the given path.

        :param extract_all: Whether to extract every YAML file found under
            `tasks/`, `handlers/`, `vars/`, and `defaults/`. If `False`
            (the default), only each directory's `main` file is extracted.
        """
        # Extract all constituents
        meta_file = None
        if (meta_file_path := find_file(path, "meta/main")) is not None:
            meta_file = _safe_extract(MetaFile.load, meta_file_path, context)

        if extract_all:
            gather_files = find_all_files
        else:

            def gather_files(dir_path: ProjectPath) -> Sequence[ProjectPath]:
                main_file = find_file(dir_path, "main")
                return [main_file] if main_file is not None else []

        task_files = _safe_extract_all(
            TaskFile.load, gather_files(path.join("tasks")), context
        )
        handler_files = _safe_extract_all(
            HandlerFile.load, gather_files(path.join("handlers")), context
        )
        vars_files = _safe_extract_all(
            VariableFile.load, gather_files(path.join("vars")), context
        )
        defaults_files = _safe_extract_all(
            VariableFile.load, gather_files(path.join("defaults")), context
        )

        return Role(
            path=path.relative,
            task_files=SourceFileMap(task_files, prefix="tasks/"),
            handler_files=SourceFileMap(handler_files, prefix="handlers/"),
            role_var_files=SourceFileMap(vars_files, prefix="vars/"),
            default_var_files=SourceFileMap(defaults_files, prefix="defaults/"),
            meta_file=meta_file,
        )
