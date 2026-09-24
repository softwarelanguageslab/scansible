from __future__ import annotations

from typing import TYPE_CHECKING, final

from scansible import ast

from .blocks import BlockBuilder
from .result import BuildResult
from .tasks import task_builder_factory

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .. import representation as rep
    from .context import BuildContext


@final
class TaskListBuilder:
    def __init__(
        self, context: BuildContext, tasks: Sequence[ast.Block | ast.Task]
    ) -> None:
        self.context = context
        self.tasks = tasks

    def build_tasks(self, predecessors: Sequence[rep.ControlNode]) -> BuildResult:
        result = BuildResult.empty(predecessors)

        for child in self.tasks:
            if isinstance(child, ast.Block):
                child_result = BlockBuilder(self.context, child).build_block(
                    result.next_predecessors
                )
            else:
                child_result = task_builder_factory(self.context, child).build_task(
                    result.next_predecessors
                )

            result = result.chain(child_result)

        return result
