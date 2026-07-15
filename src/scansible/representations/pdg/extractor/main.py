from __future__ import annotations

from typing import cast, final

from collections.abc import Sequence
from pathlib import Path

import loguru
from loguru import logger

from scansible.representations import structural as struct
from scansible.representations.structural import Position

from .. import representation as rep
from .context import ExtractionContext
from .playbook import PlaybookExtractor
from .role import RoleExtractor


def extract_pdg(
    path: Path,
    role_search_paths: Sequence[Path],
    *,
    as_pb: bool | None = None,
    lenient: bool = True,
) -> ExtractionContext:
    """
    Extract a PDG for a project at a given path.

    :param      path:                      The path to the project.
    :type       path:                      Path
    :param      role_search_paths:         The role search paths.
    :type       role_search_paths:         { type_description }
    :param      as_pb:                     Whether the project should be
                                           extracted as a playbook (if True), a
                                           role (if False), or autodetection
                                           (default).
    :type       as_pb:                     bool | None
    :param      lenient:                   Whether the extraction should be
                                           lenient.
    :type       lenient:                   bool

    :returns:   The extraction context resulting from extraction.
    :rtype:     ExtractionContext
    """
    if as_pb is None:
        as_pb = not _project_is_role(path)

    if as_pb:
        model = struct.extract_playbook(path, lenient=lenient)
    else:
        model = struct.extract_role(path, lenient=lenient, extract_all=False)

    return StructuralGraphExtractor(model, role_search_paths, lenient).extract()


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
class StructuralGraphExtractor:
    def __init__(
        self,
        model: struct.AST,
        role_search_paths: Sequence[Path],
        lenient: bool,
    ) -> None:
        self.model = model
        graph = rep.Graph()

        for bt in model.broken_tasks:
            logger.error(bt.reason)
        for bf in model.broken_files:
            logger.bind(location=bf.path).error(bf.reason)

        self.context = ExtractionContext(
            graph, model, role_search_paths, lenient=lenient
        )

    def extract(self) -> ExtractionContext:
        # Set up capturing warning and error messages so they can be added to
        # the context.
        log_handle = logger.add(
            self._capture_log_message, level="WARNING", format="{level} - {message}"
        )

        if self.model.is_playbook:
            self._extract_playbook()
        else:
            self._extract_role()

        logger.remove(log_handle)

        return self.context

    def _capture_log_message(self, message: loguru.Message) -> None:
        location = message.record.get("extra", {}).get("location")
        if isinstance(location, Position):
            if not location.is_synthetic:
                location = (
                    str(location.file),
                    location.start_line,
                    location.start_column,
                )
            else:
                location = None
        if location is not None and location[0] == "unknown file":
            location = None
        reason = str(message)
        self.context.record_extraction_error(reason, location)

    def _extract_role(self) -> None:
        _ = RoleExtractor(
            self.context,
            cast(struct.Role, self.model.root),
        ).extract_role()

    def _extract_playbook(self) -> None:
        PlaybookExtractor(
            self.context,
            cast(struct.Playbook, self.model.root),
        ).extract()
