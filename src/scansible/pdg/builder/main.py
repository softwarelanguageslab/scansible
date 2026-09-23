from __future__ import annotations

from typing import cast, final

from collections.abc import Sequence
from datetime import datetime
from pathlib import Path

import loguru
from loguru import logger

from scansible import ast
from scansible.utils import Location

from .. import representation as rep
from .context import BuildContext
from .playbook import PlaybookBuilder
from .role import RoleBuilder


def build_pdg(
    path: Path,
    role_search_paths: Sequence[Path],
    *,
    as_pb: bool | None = None,
    lenient: bool = True,
) -> BuildContext:
    """
    Build a PDG for a project at a given path.

    :param      path:                      The path to the project.
    :param      role_search_paths:         The role search paths.
    :param      as_pb:                     Whether the project should be
                                           built as a playbook (if True), a
                                           role (if False), or autodetection
                                           (default).
    :param      lenient:                   Whether the builder should be
                                           lenient.

    :returns:   The build context resulting from build process.
    """
    start_time = datetime.now()

    if as_pb is None:
        as_pb = not _project_is_role(path)

    if as_pb:
        model = ast.extract_playbook(path, lenient=lenient)
    else:
        model = ast.extract_role(path, lenient=lenient, extract_all=False)

    context = PDGBuilder(model, role_search_paths, lenient=lenient).build()

    elapsed = (datetime.now() - start_time).total_seconds()
    graph = context.graph
    logger.info(
        f"Built PDG of {graph.num_nodes} nodes and {graph.num_edges} edges in {elapsed:.2f}s"
    )

    return context


def _project_is_role(path: Path) -> bool:
    if path.is_dir() and any(
        (path / child).is_dir()
        for child in ("tasks", "defaults", "handlers", "vars", "meta")
    ):
        return True
    if path.is_file() and path.suffix.lower() in (".yml", ".yaml"):
        return False
    raise ValueError(
        f"Could not auto-detect whether project at {path} is a role or a playbook"
    )


@final
class PDGBuilder:
    def __init__(
        self, model: ast.AST, role_search_paths: Sequence[Path], *, lenient: bool
    ) -> None:
        self.model = model
        graph = rep.Graph()

        for bt in model.broken_tasks:
            logger.error(bt.reason)
        for bf in model.broken_files:
            logger.bind(location=bf.path).error(bf.reason)

        self.context = BuildContext(graph, model, role_search_paths, lenient=lenient)

    def build(self) -> BuildContext:
        # Set up capturing warning and error messages so they can be added to
        # the context.
        log_handle = logger.add(
            self._capture_log_message, level="WARNING", format="{level} - {message}"
        )

        if self.model.is_playbook:
            self._build_playbook()
        else:
            self._build_role()

        logger.remove(log_handle)

        return self.context

    def _capture_log_message(self, message: loguru.Message) -> None:
        bound_location = message.record.get("extra", {}).get("location")
        location = (
            bound_location if bound_location is not None else Location.synthetic()
        )
        reason = str(message)
        self.context.record_build_error(reason, location)

    def _build_role(self) -> None:
        _ = RoleBuilder(self.context, cast(ast.Role, self.model.root)).build_role()

    def _build_playbook(self) -> None:
        PlaybookBuilder(self.context, cast(ast.Playbook, self.model.root)).build()
