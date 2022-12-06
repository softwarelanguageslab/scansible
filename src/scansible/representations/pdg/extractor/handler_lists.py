from __future__ import annotations

from typing import Sequence

from scansible.representations.structural import Block, Handler

from .. import representation as rep
from .blocks import BlockExtractor
from .tasks import task_extractor_factory
from .var_context import ScopeLevel
from .context import ExtractionContext
from .result import ExtractionResult

class HandlerListExtractor:

    def __init__(self, context: ExtractionContext, handlers: Sequence[Block | Handler]) -> None:
        self.context = context
        self.handlers = handlers

    def extract_handlers(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        # TODO: I'm assuming that the handlers are only the top-level ones, i.e. a handler block
        # is notified using the block name, and the inner task names don't matter. This should
        # be verified.
        # TODO: The above with import_tasks in handlers.
        # TODO: The conditions here can be improved.

        result = ExtractionResult.empty(predecessors)

        # For each handler, we insert a condition node first, since handlers don't always execute.
        # TODO: Link the conditions to the tasks that notify the handlers.

        for child in self.handlers:
            cond = rep.Conditional()
            self.context.graph.add_node(cond)
            for pred in result.next_predecessors:
                self.context.graph.add_edge(pred, cond, rep.ORDER)

            if isinstance(child, Block):
                child_result = BlockExtractor(self.context, child).extract_block([cond])
            else:
                child_result = task_extractor_factory(self.context, child).extract_task([cond])

            # next predecessors are either the condition (in case the handler is skipped)
            # or the next predecessors of the handler itself.
            result = result.chain(child_result).merge(ExtractionResult([cond], [], [cond]))

        return result
