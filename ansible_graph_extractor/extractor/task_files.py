from __future__ import annotations

from voyager.models.structural.role import TaskFile

from ..models import nodes as n
from .blocks import BlockExtractor
from .var_context import ScopeLevel
from .context import ExtractionContext, TaskExtractionResult

class TaskFileExtractor:

    def __init__(self, context: ExtractionContext, task_file: TaskFile) -> None:
        self.context = context
        self.task_file = task_file

    def extract_tasks(self, predecessors: list[n.ControlNode]) -> TaskExtractionResult:
        all_added_nodes = []
        for block in self.task_file:
            with self.context.vars.enter_scope(ScopeLevel.BLOCK_VARS):
                block_result = BlockExtractor(self.context, block).extract_block(predecessors)
                all_added_nodes.extend(block_result.added_control_nodes)
                predecessors = block_result.next_predecessors

        return TaskExtractionResult(
                added_control_nodes=all_added_nodes,
                next_predecessors=predecessors)
