from __future__ import annotations

from typing import Sequence

from pathlib import Path

import loguru
from loguru import logger

from scansible.representations import structural as struct

from .. import representation as rep
from .var_context import ScopeLevel, VarContext
from .role import RoleExtractor
from .playbook import PlaybookExtractor
from .context import ExtractionContext

def extract_pdg(path: Path, project_id: str, project_rev: str, role_search_path: Path, *, as_pb: bool | None = None, lenient: bool = True) -> ExtractionContext:
    """
    Extract a PDG for a project at a given path.

    :param      path:         The path to the project.
    :type       path:         Path
    :param      project_id:   The project identifier.
    :type       project_id:   str
    :param      project_rev:  The project revision.
    :type       project_rev:  str
    :param      as_pb:        Whether the project should be extracted as a
                              playbook (if True), a role (if False), or
                              autodetection (default).
    :type       as_pb:        bool | None
    :param      lenient:      Whether the extraction should be lenient.
    :type       lenient:      bool

    :returns:   The extraction context resulting from extraction.
    :rtype:     ExtractionContext
    """
    if as_pb is None:
        as_pb = not _project_is_role(path)

    if as_pb:
        model = struct.extract_playbook(path, project_id, project_rev, lenient=lenient)
    else:
        model = struct.extract_role(path, project_id, project_rev, lenient=lenient, extract_all=False)

    return StructuralGraphExtractor(model, role_search_path, lenient).extract()


def _project_is_role(path: Path) -> bool:
    if path.is_dir() and any((path / child).is_dir() for child in ('tasks', 'defaults', 'handlers', 'vars', 'meta')):
        return True
    if path.is_file() and path.suffix.lower() in ('.yml', '.yaml'):
        return False
    raise ValueError(f'Could not auto-detect whether project at {path} is a role or a playbook')


class StructuralGraphExtractor:

    def __init__(self, model: struct.StructuralModel, role_search_path: Path, lenient: bool) -> None:
        self.model = model
        graph = rep.Graph(model.id, model.version)
        for logstr in model.logs:
            logger.debug(logstr)

        for bt in model.root.broken_tasks:
            logger.error(bt.reason)
        for bf in model.root.broken_files:
            logger.bind(location=bf.path).error(bf.reason)

        self.context = ExtractionContext(graph, model, role_search_path, lenient=lenient)

    def extract(self) -> ExtractionContext:
        # Set up capturing warning and error messages so they can be added to
        # the context.
        log_handle = logger.add(self._capture_log_message, level='WARNING', format='{level} - {message}')

        if self.model.is_playbook:
            self._extract_playbook()
        else:
            self._extract_role()

        logger.remove(log_handle)

        # logger.info('Finished extraction, now adding transitive edges')
        # self.add_transitive_edges()

        return self.context

    def _capture_log_message(self, message: loguru.Message) -> None:
        location = message.record.get('extra', {}).get('location')
        if location is not None and location[0] == 'unknown file':
            location = None
        reason = str(message)
        self.context.record_extraction_error(reason, location)

    def _extract_role(self) -> None:
        RoleExtractor(
            self.context,
            self.model.root,  # type: ignore[arg-type]
        ).extract_role()

    def _extract_playbook(self) -> None:
        PlaybookExtractor(
            self.context,
            self.model.root,  # type: ignore[arg-type]
        ).extract()

    def add_transitive_edges(self) -> None:
        prev_num_edges = 0
        while prev_num_edges != self.context.graph.number_of_edges():
            print(prev_num_edges)
            prev_num_edges = self.context.graph.number_of_edges()
            for node in self.context.graph:
                if not isinstance(node, rep.Task):
                    continue
                for succ, succ_edges in list(self.context.graph[node].items()):
                    if not any(isinstance(e['type'], rep.Order) for e in succ_edges.values()):
                        continue

                    for trans_succ, succ_succ_edges in self.context.graph[succ].items():
                        if not any(isinstance(e['type'], rep.Order) for e in succ_succ_edges.values()):
                            continue

                        # print(f'add {node} -> {trans_succ}')
                        self.context.graph.add_edge(node, trans_succ, rep.ORDER_TRANS)
