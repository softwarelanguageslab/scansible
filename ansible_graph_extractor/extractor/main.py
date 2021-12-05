from typing import Any, Optional, Union

from pathlib import Path

from loguru import logger

from voyager.models.structural.role import (
        Block, HandlerFile, DefaultVarFile, RoleVarFile, StructuralRoleModel, Task, TaskFile)
from voyager.models.structural.abstract import AbstractVariableFile, ContainerFile

from ..models.edges import DEF, Order, ORDER, ORDER_TRANS, Keyword
from ..models import nodes as n
from ..models.graph import Graph
from .var_context import ScopeLevel, VarContext
from .var_files import VariableFileExtractor
from .task_files import TaskFileExtractor
from .context import ExtractionContext, Files

def extract_structural_graph(role_path: Path, role_id: str, role_rev: str) -> Graph:
    model = StructuralRoleModel.create(role_path, role_id, role_rev)
    return StructuralGraphExtractor(role_path, model).extract()


class StructuralGraphExtractor:

    def __init__(self, role_path: Path, model: StructuralRoleModel) -> None:
        graph = Graph(model.role_id, model.role_rev)
        self.context = ExtractionContext(graph, model.role_root, role_path)

    def extract(self) -> Graph:
        with self.context.vars.enter_scope(ScopeLevel.ROLE_DEFAULTS), self.context.vars.enter_scope(ScopeLevel.ROLE_VARS):
            if self.context.files.main_defaults_file is not None:
                VariableFileExtractor(self.context, self.context.files.main_defaults_file).extract_variables(ScopeLevel.ROLE_DEFAULTS)

            if self.context.files.main_var_file is not None:
                VariableFileExtractor(self.context, self.context.files.main_var_file).extract_variables(ScopeLevel.ROLE_VARS)

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
            return self.context.graph

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
