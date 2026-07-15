"""Extraction logic for structural model."""

from __future__ import annotations

from pathlib import Path

from . import nodes
from .common import ExtractionContext
from .helpers import ProjectPath


def extract_role_metadata_file(
    path: ProjectPath, ctx: ExtractionContext
) -> nodes.MetaFile:
    """Extract the structural representation of a metadata file."""
    return nodes.MetaFile.load(path, ctx)


def extract_variable_file(
    path: ProjectPath, ctx: ExtractionContext
) -> nodes.VariableFile:
    return nodes.VariableFile.load(path, ctx)


def extract_handler_file(
    path: ProjectPath, ctx: ExtractionContext
) -> nodes.HandlerFile:
    return nodes.HandlerFile.load(path, ctx)


def extract_tasks_file(path: ProjectPath, ctx: ExtractionContext) -> nodes.TaskFile:
    return nodes.TaskFile.load(path, ctx)


def extract_playbook_file(
    pb_path: ProjectPath, ctx: ExtractionContext
) -> nodes.Playbook:
    return nodes.Playbook.load(pb_path, ctx)


def extract_playbook(path: Path, lenient: bool = True) -> nodes.AST:
    """Extract an AST for a playbook.

    :param      path:     The path to the playbook.
    :param      lenient:  Whether extraction should be lenient, i.e. ignoring broken tasks/blocks.
    """

    pb_path = ProjectPath.from_root(path)
    ctx = ExtractionContext(lenient)
    pb = extract_playbook_file(pb_path, ctx)

    return nodes.AST(
        root=pb, path=path, broken_files=ctx.broken_files, broken_tasks=ctx.broken_tasks
    )


def extract_role(
    path: Path, extract_all: bool = False, lenient: bool = True
) -> nodes.AST:
    """Extract an AST for a role.

    :param      path:         The path to the role.
    :param      extract_all:  Whether to extract all available files, or just the main files.
                              Defaults to `False`. Additional files can still be extracted using
                              `extract_task_file` or `extract_variable_file`.
    :param      lenient:      Whether extracting should be lenient, i.e. ignoring broken tasks/blocks.
    """

    role_path = ProjectPath.from_root(path)
    ctx = ExtractionContext(lenient)
    role = nodes.Role.load(role_path, ctx, extract_all)

    return nodes.AST(
        root=role,
        path=path,
        broken_files=ctx.broken_files,
        broken_tasks=ctx.broken_tasks,
    )
