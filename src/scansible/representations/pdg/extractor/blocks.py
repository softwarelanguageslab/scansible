from __future__ import annotations

from typing import Sequence

from scansible.representations.structural import Block, Task, Handler

from .. import representation as rep
from .context import ExtractionContext, TaskExtractionResult
from .tasks import task_extractor_factory
from .var_context import ScopeLevel

class BlockExtractor:

    SUPPORTED_BLOCK_ATTRIBUTES = frozenset(('name', 'block', 'rescue', 'always', 'vars'))

    def __init__(self, context: ExtractionContext, block: Block) -> None:
        self.context = context
        self.block = block
        self.location = rep.NodeLocation.fake()

    def extract_block(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        with self.context.vars.enter_scope(ScopeLevel.BLOCK_VARS):
            return self._extract_block(predecessors)

    def _extract_block(self, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        for var_name, var_value in self.block.vars.items():
            # Apparently Ansible doesn't implement overriding of block-scoped
            # variables properly. Variables registered in an inner block don't
            # shadow variables registered in an outer block. However, it's
            # confirmed to be a bug, so we'll handle it as if it were
            # implemented correctly.
            self.context.vars.register_variable(var_name, expr=var_value, level=ScopeLevel.BLOCK_VARS, name_location=self.location, init_location=self.location)

        # A block without a list of tasks should be impossible
        block_result = self._extract_children(self.block.block, predecessors)

        # Predecessors of the first rescue child can be any of the nodes
        # in the main block, since any of the children could have failed.
        # TODO: But perhaps not those tasks in a nested block whose failure was
        # already handled by a nested rescue?
        # TODO: Should we add conditional execution on the result registered
        # by a task?
        rescue_result = self._extract_children(self.block.rescue, block_result.added_control_nodes)

        # Predecessors of the always block is either the last main block task,
        # or the last rescue block task if it was called.
        # TODO: What happens when a task in a rescue block fails itself?
        # TODO: What happens when a main block task fails and there is no
        # rescue block? Will the always block still be executed? If so, the below
        # is correct. If not, the below is incorrect, since if there's no rescue
        # block, it will link all main block tasks to the first always task.
        always_result = self._extract_children(self.block.always, block_result.next_predecessors + rescue_result.next_predecessors)

        for kw, _ in self.block._get_non_default_attributes():
            if kw not in self.SUPPORTED_BLOCK_ATTRIBUTES and kw != 'raw':
                self.context.graph.errors.append(f'Unsupported block keyword {kw}!')

        # Successors of a block are as follows:
        # - If always block is defined: The last node(s) of always block (always_result.pred)
        #   -> always_result.next_predecessors contains this value
        # - Otherwise, if rescue block is defined: Last node(s) of main block + last node(s) of rescue block (block_result.pred + rescue_result.pred)
        #   -> always_result.next_predecessors contains this value, since it never overwrote the predecessors.
        # - Otherwise, last node(s) of main block (block_result.pred)
        #   -> Cannot use always_result.next_predecessors as rescue_result.next_predecessors is ALL nodes in the main block if there is no rescue block
        #      TODO: Depending on the outcome of the TODO above, we may need to change this
        if not self.block.always and not self.block.rescue:
            next_predecessors = block_result.next_predecessors
        else:
            next_predecessors = always_result.next_predecessors
        return TaskExtractionResult(
                added_control_nodes=block_result.added_control_nodes + rescue_result.added_control_nodes + always_result.added_control_nodes,
                added_variable_nodes=block_result.added_variable_nodes + rescue_result.added_variable_nodes + always_result.added_variable_nodes,
                next_predecessors=next_predecessors)

    def _extract_children(self, child_list: Sequence[Task | Block | Handler], predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        added = []
        added_vars = []
        for child in child_list:
            if isinstance(child, Block):
                prev_result = BlockExtractor(self.context, child).extract_block(predecessors)
            else:
                assert isinstance(child, Task)
                task_extractor = task_extractor_factory(self.context, child)
                prev_result = task_extractor.extract_task(predecessors)

            predecessors = prev_result.next_predecessors
            added_vars.extend(prev_result.added_variable_nodes)
            added.extend(prev_result.added_control_nodes)

        return TaskExtractionResult(next_predecessors=predecessors, added_control_nodes=added, added_variable_nodes=added_vars)
