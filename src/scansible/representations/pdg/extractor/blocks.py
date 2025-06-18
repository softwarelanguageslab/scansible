from __future__ import annotations

from typing import Sequence

from loguru import logger

from scansible.representations.structural import Block, Task

from .. import representation as rep
from .context import ExtractionContext
from .expressions import EnvironmentType, RecursiveDefinitionError
from .result import ExtractionResult


class BlockExtractor:
    SUPPORTED_BLOCK_ATTRIBUTES = frozenset(
        (
            "name",
            "block",
            "rescue",
            "always",
            "vars",
            "become",
            "become_user",
            "become_method",
        )
    )

    def __init__(self, context: ExtractionContext, block: Block) -> None:
        self.context = context
        self.block = block
        self.location = context.get_location(block)
        self.logger = logger.bind(location=block.location)

    def extract_block(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        with self.context.vars.enter_scope(EnvironmentType.BLOCK_VARS):
            return self._extract_block(predecessors)

    def _extract_block(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        for var_name, var_value in self.block.vars.items():
            # Apparently Ansible doesn't implement overriding of block-scoped
            # variables properly. Variables registered in an inner block don't
            # shadow variables registered in an outer block. However, it's
            # confirmed to be a bug, so we'll handle it as if it were
            # implemented correctly.
            self.context.vars.define_initialised_variable(
                var_name, EnvironmentType.BLOCK_VARS, var_value
            )

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
            result = result.merge(
                self._extract_children(self.block.rescue, result.added_control_nodes)
            )  # type: ignore[arg-type]

        # Predecessors of the always block is either the last main block task,
        # or the last rescue block task if it was called.
        # TODO: What happens when a task in a rescue block fails itself?
        # TODO: What happens when a main block task fails and there is no
        # rescue block? Will the always block still be executed? If so, the below
        # is incorrect, since it only has the last task of both as the predecessors.
        if self.block.always:
            # If there's an always block, the next predecessors of the next element
            # will always be the last task of the always block, so use `chain`.
            result = result.chain(
                self._extract_children(self.block.always, result.next_predecessors)
            )  # type: ignore[arg-type]

        for misc_kw in ("become", "become_user", "become_method"):
            kw_val = getattr(self.block, misc_kw)
            if self.block.is_default(misc_kw, kw_val):
                continue

            prev_value: rep.DataNode | None = None

            for ctrl_node in result.added_control_nodes:
                if not isinstance(ctrl_node, rep.Task):
                    continue

                in_edges = self.context.graph.in_edges(ctrl_node, data="type")
                has_overridden_kw = any(
                    in_edge.keyword == misc_kw
                    for _, _, in_edge in in_edges
                    if isinstance(in_edge, rep.Keyword)
                )
                if has_overridden_kw:
                    continue

                try:
                    value = prev_value or self.context.vars.build_expression(kw_val)
                except RecursiveDefinitionError as e:
                    self.logger.error(e)
                    continue

                if isinstance(value, rep.Literal):
                    prev_value = value

                self.context.graph.add_edge(
                    value, ctrl_node, rep.Keyword(keyword=misc_kw)
                )

        for kw, _ in self.block.__get_non_default_attributes__():
            if kw not in self.SUPPORTED_BLOCK_ATTRIBUTES and kw not in (
                "location",
                "raw",
                "parent",
            ):
                self.logger.warning(f"Unsupported block keyword {kw!r}!")

        return result

    def _extract_children(
        self,
        child_list: Sequence[Task | Block],
        predecessors: Sequence[rep.ControlNode],
    ) -> ExtractionResult:
        from .task_lists import TaskListExtractor

        return TaskListExtractor(self.context, child_list).extract_tasks(predecessors)
