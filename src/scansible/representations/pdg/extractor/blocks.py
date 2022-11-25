from __future__ import annotations

from typing import Sequence

from scansible.representations.structural import Block, Task, Handler

from .. import representation as rep
from .context import ExtractionContext
from .result import ExtractionResult
from .tasks import task_extractor_factory
from .var_context import ScopeLevel

class BlockExtractor:

    SUPPORTED_BLOCK_ATTRIBUTES = frozenset(('name', 'block', 'rescue', 'always', 'vars'))

    def __init__(self, context: ExtractionContext, block: Block) -> None:
        self.context = context
        self.block = block
        self.location = context.get_location(block)

    def extract_block(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.context.vars.enter_scope(ScopeLevel.BLOCK_VARS):
            return self._extract_block(predecessors)

    def _extract_block(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        for var_name, var_value in self.block.vars.items():
            # Apparently Ansible doesn't implement overriding of block-scoped
            # variables properly. Variables registered in an inner block don't
            # shadow variables registered in an outer block. However, it's
            # confirmed to be a bug, so we'll handle it as if it were
            # implemented correctly.
            self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.BLOCK_VARS)

        # A block without a list of tasks should be impossible
        # TODO: Typing here is messed up, since Block's children could be handlers too.
        result = self._extract_children(self.block.block, predecessors)  # type: ignore[arg-type]

        # Predecessors of the first rescue child can be any of the nodes
        # in the main block, since any of the children could have failed.
        # TODO: But perhaps not those tasks in a nested block whose failure was
        # already handled by a nested rescue?
        # TODO: Should we add conditional execution on the result registered
        # by a task?
        if self.block.rescue:
            # `rescue` is sort of a branch, so merge the two results so we have
            # two potential predecessors: The last task of the block, and the
            # last task of the rescue.
            result = result.merge(self._extract_children(self.block.rescue, result.added_control_nodes))  # type: ignore[arg-type]

        # Predecessors of the always block is either the last main block task,
        # or the last rescue block task if it was called.
        # TODO: What happens when a task in a rescue block fails itself?
        # TODO: What happens when a main block task fails and there is no
        # rescue block? Will the always block still be executed? If so, the below
        # is incorrect, since it only has the last task of both as the predecessors.
        if self.block.always:
            # If there's an always block, the next predecessors of the next element
            # will always be the last task of the always block, so use `chain`.
            result = result.chain(self._extract_children(self.block.always, result.next_predecessors))  # type: ignore[arg-type]

        for kw, _ in self.block._get_non_default_attributes():
            if kw not in self.SUPPORTED_BLOCK_ATTRIBUTES and kw != 'raw':
                self.context.graph.errors.append(f'Unsupported block keyword {kw}!')

        return result

    def _extract_children(self, child_list: Sequence[Task | Block], predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        from .task_lists import TaskListExtractor
        return TaskListExtractor(self.context, child_list).extract_tasks(predecessors)
