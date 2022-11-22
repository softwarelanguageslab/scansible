from __future__ import annotations

from typing import Sequence

from scansible.representations.structural import Block, Task

from .. import representation as rep
from .blocks import BlockExtractor
from .tasks import task_extractor_factory
from .var_context import ScopeLevel
from .context import ExtractionContext, TaskExtractionResult

class TaskListExtractor:

    def __init__(self, context: ExtractionContext, tasks: Sequence[Block | Task]) -> None:
        self.context = context
        self.tasks = tasks

    def extract_tasks(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        all_added_nodes = []
        all_added_var_nodes = []
        for child in self.tasks:
            if isinstance(child, Block):
                intermediate_result = BlockExtractor(self.context, child).extract_block(predecessors)
            else:
                intermediate_result = task_extractor_factory(self.context, child).extract_task(predecessors)

            all_added_var_nodes.extend(intermediate_result.added_variable_nodes)
            all_added_nodes.extend(intermediate_result.added_control_nodes)
            predecessors = intermediate_result.next_predecessors

        return TaskExtractionResult(
                added_control_nodes=all_added_nodes,
                added_variable_nodes=all_added_var_nodes,
                next_predecessors=predecessors)
