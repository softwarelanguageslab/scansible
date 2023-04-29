from __future__ import annotations

from typing import Sequence

from loguru import logger

from scansible.representations.structural import Block, Handler

from .. import representation as rep
from .blocks import BlockExtractor
from .context import ExtractionContext
from .result import ExtractionResult
from .tasks import task_extractor_factory


class HandlerListExtractor:
    def __init__(
        self, context: ExtractionContext, handlers: Sequence[Block | Handler]
    ) -> None:
        self.context = context
        self.handlers = handlers

    def extract_handlers(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        # TODO: I'm assuming that the handlers are only the top-level ones, i.e. a handler block
        # is notified using the block name, and the inner task names don't matter. This should
        # be verified.
        # TODO: The above with import_tasks in handlers.
        # TODO: The conditions here can be improved.

        result = ExtractionResult.empty(predecessors)

        # For each handler, we insert a condition node first, since handlers don't always execute.
        # TODO: Link the conditions to the tasks that notify the handlers.

        for child in self.handlers:
            if isinstance(child, Block):
                child_result = BlockExtractor(self.context, child).extract_block(
                    predecessors
                )
            else:
                child_result = task_extractor_factory(self.context, child).extract_task(
                    predecessors
                )

            topics = set(child.listen if isinstance(child, Handler) else [])
            if child.name is not None:
                topics.add(child.name)
            notifiers: set[rep.Task] = set()
            for topic in topics:
                notifiers |= self.context.handler_notifications[topic]

            if not topics:
                logger.warning(f"Handler {child} is not listening to anything")

            if not notifiers:
                logger.warning(f"Handler {child.name or child} is never notified")

            for handler_node in child_result.added_control_nodes:
                if not isinstance(handler_node, rep.Task):
                    continue
                for notifier in notifiers:
                    self.context.graph.add_edge(notifier, handler_node, rep.NOTIFIES)

            # next predecessors are either the condition (in case the handler is skipped)
            # or the next predecessors of the handler itself.
            result = result.chain(child_result)

        return result
