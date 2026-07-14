"""Extraction logic for structural model."""

from __future__ import annotations

from typing import Callable

from functools import partial
from pathlib import Path

from pydantic import ValidationError

from scansible.utils import actions

from . import ansible_types as ans
from . import ast, loaders
from .ast import ExtractionContext
from .helpers import (
    ProjectPath,
    capture_output,
    find_all_files,
    find_file,
    prevent_undesired_operations,
)


def extract_role_metadata_file(
    path: ProjectPath, ctx: ExtractionContext
) -> ast.MetaFile:
    """Extract the structural representation of a metadata file."""
    return ast.MetaFile.load(path, ctx)


def extract_variable_file(
    path: ProjectPath, ctx: ExtractionContext
) -> ast.VariableFile:
    return ast.VariableFile.load(path, ctx)


def extract_handler_file(path: ProjectPath, ctx: ExtractionContext) -> ast.HandlerFile:
    return ast.HandlerFile.load(path, ctx)


def extract_tasks_file(path: ProjectPath, ctx: ExtractionContext) -> ast.TaskFile:
    return ast.TaskFile.load(path, ctx)


def extract_play(ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext) -> ast.Play:
    return ast.Play.model_validate(ds, context=ctx)


def extract_playbook_child(
    ds: dict[str, ans.AnsibleValue], ctx: ExtractionContext
) -> ast.Play | None:
    if any(actions.is_import_playbook(directive) for directive in ds):
        # Ignore import_playbook for now. The imported playbook can be checked as a separate entrypoint.
        return None
    else:
        return extract_play(ds, ctx)


def extract_playbook_file(
    pb_path: ProjectPath, lenient: bool
) -> tuple[ast.Playbook, str]:
    ctx = ExtractionContext(lenient)

    with capture_output() as output, prevent_undesired_operations():
        ds, _ = loaders.load_playbook(pb_path)

        # Parse the plays in the playbook
        plays: list[ast.Play] = []
        for play_ds in ds:
            try:
                play = extract_playbook_child(play_ds, ctx)
            except (ans.AnsibleError, loaders.LoadError) as e:
                if not ctx.lenient:
                    raise
                ctx.broken_tasks.append(ast.BrokenTask(raw=play_ds, reason=str(e)))
                continue

            if play is not None:
                plays.append(play)

    pb = ast.Playbook(plays=plays, path=pb_path.relative, broken_tasks=ctx.broken_tasks)
    return pb, output.getvalue()


def extract_playbook(path: Path, lenient: bool = True) -> ast.AST:
    """
    Extract a structural model from a playbook.

    :param      path:     The path to the playbook.
    :type       path:     Path
    :param      lenient:  Whether extraction should be lenient, i.e. ignoring
                          broken tasks/blocks.
    :type       lenient:  bool

    :returns:   Extracted structural model.
    :rtype:     StructuralModel
    """

    pb_path = ProjectPath.from_root(path)
    pb, _ = extract_playbook_file(pb_path, lenient=lenient)

    return ast.AST(root=pb, path=path)


def extract_role(
    path: Path, extract_all: bool = False, lenient: bool = True
) -> ast.AST:
    """
    Extract a structural model from a role.

    :param      path:         The path to the role.
    :type       path:         Path
    :param      extract_all:  Whether to extract all available files, or just
                              the main files. Defaults to `False`. Additional
                              files can still be extracted using
                              `extract_task_file` or `extract_variable_file`.
    :type       extract_all:  bool
    :param      lenient:      Whether extracting should be lenient, i.e.
                              ignoring broken tasks/blocks.
    :type       lenient:      bool

    :returns:   Extracted structural model.
    :rtype:     StructuralModel
    """

    role_path = ProjectPath.from_root(path)
    ctx = ExtractionContext(lenient)

    # Extract all constituents
    task_files: dict[str, ast.TaskFile] = {}
    handler_files: dict[str, ast.HandlerFile] = {}
    vars_files: dict[str, ast.VariableFile] = {}
    defaults_files: dict[str, ast.VariableFile] = {}
    meta_files: dict[str, ast.MetaFile] = {}

    with capture_output(), prevent_undesired_operations():
        meta_file_path = find_file(role_path, "meta/main")
        _safe_extract(
            extract_role_metadata_file,
            meta_file_path,
            meta_files,
            ctx,
        )
        meta_file = next(iter(meta_files.values())) if meta_files else None

        if extract_all:
            get_dir = partial(ProjectPath, role_path.absolute)

            _safe_extract_all(
                extract_tasks_file,
                get_dir("tasks"),
                task_files,
                ctx,
            )
            _safe_extract_all(
                extract_handler_file,
                get_dir("handlers"),
                handler_files,
                ctx,
            )
            _safe_extract_all(
                extract_variable_file,
                get_dir("vars"),
                vars_files,
                ctx,
            )
            _safe_extract_all(
                extract_variable_file,
                get_dir("defaults"),
                defaults_files,
                ctx,
            )
        else:

            def get_main_path(dirname: str) -> ProjectPath | None:
                return find_file(role_path.join(dirname), "main")

            _safe_extract(
                extract_tasks_file,
                get_main_path("tasks"),
                task_files,
                ctx,
            )
            _safe_extract(
                extract_handler_file,
                get_main_path("handlers"),
                handler_files,
                ctx,
            )
            _safe_extract(
                extract_variable_file,
                get_main_path("defaults"),
                defaults_files,
                ctx,
            )
            _safe_extract(
                extract_variable_file,
                get_main_path("vars"),
                vars_files,
                ctx,
            )

    role = ast.Role(
        path=role_path.relative,
        task_files=ast.SourceFileMap(task_files.values(), prefix="tasks/"),
        handler_files=ast.SourceFileMap(handler_files.values(), prefix="handlers/"),
        role_var_files=ast.SourceFileMap(vars_files.values(), prefix="vars/"),
        default_var_files=ast.SourceFileMap(
            defaults_files.values(), prefix="defaults/"
        ),
        meta_file=meta_file,
        broken_files=ctx.broken_files,
        broken_tasks=ctx.broken_tasks,
    )

    return ast.AST(root=role, path=path)


type Extractor[T] = Callable[[ProjectPath, ExtractionContext], T]


def _safe_extract[T](
    extractor: Extractor[T],
    file_path: ProjectPath | None,
    file_dict: dict[str, T],
    ctx: ExtractionContext,
) -> None:
    if file_path is None:
        return

    try:
        extracted_file = extractor(file_path, ctx)
        file_dict["/".join(file_path.relative.parts[1:])] = extracted_file
    except (ans.AnsibleError, loaders.LoadError, ValidationError) as e:
        ctx.broken_files.append(ast.BrokenFile(path=file_path.relative, reason=str(e)))


def _safe_extract_all[T](
    extractor: Extractor[T],
    dir_path: ProjectPath,
    file_dict: dict[str, T],
    ctx: ExtractionContext,
) -> None:
    if not dir_path.absolute.is_dir():
        return

    for child_path in find_all_files(dir_path):
        _safe_extract(extractor, child_path, file_dict, ctx)
