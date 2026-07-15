"""Extraction logic for the AST."""

from __future__ import annotations

from pathlib import Path

from scansible.utils import ProjectPath

from . import nodes
from .common import ExtractionContext


def extract_playbook(path: Path, lenient: bool = True) -> nodes.AST:
    """Extract the AST representation of a playbook.

    :param path: The path to the playbook.
    :param lenient: Whether extraction should be lenient, i.e. ignoring broken tasks/blocks.
    """

    pb_path = ProjectPath.from_root(path)
    ctx = ExtractionContext(lenient)
    pb = nodes.Playbook.load(pb_path, ctx)

    return nodes.AST(
        root=pb,
        path=path,
        broken_files=ctx.broken_files,
        broken_tasks=ctx.broken_tasks,
    )


def extract_role(
    path: Path, extract_all: bool = False, lenient: bool = True
) -> nodes.AST:
    """Extract the AST representation of a role.

    :param path: The path to the role.
    :param extract_all: Whether to extract all available files, or just the main files.
        Defaults to `False`. Additional files can still be extracted using
        `extract_task_file` or `extract_variable_file`.
    :param lenient: Whether extracting should be lenient, i.e. ignoring broken tasks/blocks.
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
