from __future__ import annotations

from typing import Sequence

from scansible.representations.structural import Block, Task

from .. import representation as rep
from .blocks import BlockExtractor
from .tasks import task_extractor_factory
from .var_context import ScopeLevel
from .context import ExtractionContext
from .result import ExtractionResult

class TaskListExtractor:

    def __init__(self, context: ExtractionContext, tasks: Sequence[Block | Task]) -> None:
        self.context = context
        self.tasks = tasks

    def extract_tasks(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        result = ExtractionResult.empty(predecessors)

        for child in self.tasks:
            if isinstance(child, Block):
                child_result = BlockExtractor(self.context, child).extract_block(result.next_predecessors)
            else:
                child_result = task_extractor_factory(self.context, child).extract_task(result.next_predecessors)

            result = result.chain(child_result)

        return result
