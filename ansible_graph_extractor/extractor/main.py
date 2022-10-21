from typing import Any, Optional, Union

from pathlib import Path

from loguru import logger

from voyager.models.structural.role import (
        Block, HandlerFile, DefaultVarFile, RoleVarFile, StructuralRoleModel, Task, TaskFile)
from voyager.models.structural.playbook import (
        StructuralPlaybookModel, Variable, VarFile)
from voyager.models.structural.abstract import AbstractVariableFile, ContainerFile

from ..models.edges import DEF, Order, ORDER, ORDER_TRANS, Keyword
from ..models import nodes as n
from ..models.graph import Graph
from .var_context import ScopeLevel, VarContext
from .var_files import VariableFileExtractor
from .task_files import TaskFileExtractor
from .context import ExtractionContext, Files

def extract_structural_graph(role_path: Path, role_id: str, role_rev: str, is_pb: bool = False) -> ExtractionContext:
    if is_pb:
        model = StructuralPlaybookModel.create(role_path, role_id, role_rev)
    else:
        model = StructuralRoleModel.create(role_path, role_id, role_rev)
    return StructuralGraphExtractor(role_path, model).extract()


class StructuralGraphExtractor:

    def __init__(self, role_path: Path, model: StructuralRoleModel) -> None:
        if isinstance(model, StructuralRoleModel):
            graph = Graph(model.role_id, model.role_rev)
            graph.errors.extend([f'{bf.path}: {bf.reason}' for bf in model.role_root.broken_files])
            for logstr in model.role_root.logs:
                logger.debug(logstr)
            self.context = ExtractionContext(graph, model.role_root, role_path, False)
            self.is_pb = False
        else:
            graph = Graph(model.pb_id, model.pb_rev)
            for logstr in model.pb_root.logs:
                logger.debug(logstr)
            self.context = ExtractionContext(graph, model.pb_root, role_path, True)
            self.is_pb = True


    def extract(self) -> ExtractionContext:
        if self.is_pb:
            self._extract_pb()
        else:
            self._extract_role()
        return self.context

    def _extract_role(self) -> None:
        with self.context.vars.enter_scope(ScopeLevel.ROLE_DEFAULTS), self.context.vars.enter_scope(ScopeLevel.ROLE_VARS):
            if (df := self.context.files.main_defaults_file) is not None:
                VariableFileExtractor(self.context, df, f'{df.file_name} via initial role load').extract_variables(ScopeLevel.ROLE_DEFAULTS)

            if (vf := self.context.files.main_var_file) is not None:
                VariableFileExtractor(self.context, vf, f'{vf.file_name} via initial role load').extract_variables(ScopeLevel.ROLE_VARS)

            # Extract handlers first, as they're needed to link to tasks
            if self.context.files.main_handler_file is not None:
                self.context.graph.errors.append('I cannot handle handlers yet!')

            if self.context.files.main_task_file is not None:
                with self.context.files.enter_included_file(self.context.files.main_task_file):
                    TaskFileExtractor(self.context, self.context.files.main_task_file).extract_tasks([])
            else:
                logger.warning('No main task file')

            # logger.info('Finished extraction, now adding transitive edges')

            # self.add_transitive_edges()

    def _extract_pb(self) -> None:
        for play in self.context.role.plays:
            self.context.play = play
            with self.context.vars.enter_scope(ScopeLevel.PLAY_VARS):
                extr = VariableFileExtractor(self.context, None, f'Play {play.name} variables')
                for v in play.vars.values():
                    extr.extract_variable(v, ScopeLevel.PLAY_VARS)
                TaskFileExtractor(self.context, play.blocks).extract_tasks([])


    def add_transitive_edges(self) -> None:
        prev_num_edges = 0
        while prev_num_edges != self.context.graph.number_of_edges():
            print(prev_num_edges)
            prev_num_edges = self.context.graph.number_of_edges()
            for node in self.context.graph.nodes:
                if not isinstance(node, n.Task):
                    continue
                for succ, succ_edges in list(self.context.graph[node].items()):
                    if not any(isinstance(e['type'], Order) for e in succ_edges.values()):
                        continue

                    for trans_succ, succ_succ_edges in self.context.graph[succ].items():
                        if not any(isinstance(e['type'], Order) for e in succ_succ_edges.values()):
                            continue

                        # print(f'add {node} -> {trans_succ}')
                        self.context.graph.add_edge(node, trans_succ, ORDER_TRANS)
