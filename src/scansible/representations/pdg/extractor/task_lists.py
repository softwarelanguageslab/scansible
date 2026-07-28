from __future__ import annotations

from typing import final

from collections.abc import Sequence

from scansible.representations import ast

from .. import representation as rep
from .blocks import BlockExtractor
from .context import ExtractionContext
from .result import ExtractionResult
from .tasks import task_extractor_factory


@final
class TaskListExtractor:
    def __init__(
        self, context: ExtractionContext, tasks: Sequence[ast.Block | ast.Task]
    ) -> None:
        self.context = context
        self.tasks = tasks

    def extract_tasks(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        result = ExtractionResult.empty(predecessors)

        for child in self.tasks:
            if isinstance(child, ast.Block):
                child_result = BlockExtractor(self.context, child).extract_block(
                    result.next_predecessors
                )
            else:
                child_result = task_extractor_factory(self.context, child).extract_task(
                    result.next_predecessors
                )

            result = result.chain(child_result)

        return result
