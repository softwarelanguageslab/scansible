from __future__ import annotations

from typing import ClassVar, ContextManager, Generic, TypeVar

import abc
from collections.abc import Sequence

from scansible.representations.structural.representation import AnyValue

from ... import representation as rep
from ..result import ExtractionResult
from ..var_context import ScopeLevel
from .base import TaskExtractor

_IncludedContent = TypeVar("_IncludedContent")


class DynamicIncludesExtractor(TaskExtractor, abc.ABC, Generic[_IncludedContent]):
    CONTENT_TYPE: ClassVar[str]

    @abc.abstractmethod
    def _extract_included_name(self, args: dict[str, AnyValue]) -> AnyValue:
        """Extract included name from arguments, and pop the argument."""
        raise NotImplementedError()

    @abc.abstractmethod
    def _load_content(
        self, included_name: str
    ) -> ContextManager[_IncludedContent | None]:
        """Load and enter included content as a context manager."""
        raise NotImplementedError

    @abc.abstractmethod
    def _extract_included_content(
        self,
        included_content: _IncludedContent,
        predecessors: Sequence[rep.ControlNode],
    ) -> ExtractionResult:
        raise NotImplementedError()

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.setup_task_vars_scope(ScopeLevel.INCLUDE_PARAMS):
            abort_result = ExtractionResult.empty(predecessors)
            args = dict(self.task.args)

            included_name = self._extract_included_name(args)
            if not included_name or not isinstance(included_name, str):
                self.logger.error(f"Unknown included file name!")
                return abort_result

            if "{{" in included_name:
                # TODO: When we do handle expressions here, we should make sure
                # to check whether these expressions can or cannot use the include
                # parameters. If they cannot, we should extract the included
                # name before registering the variables.
                self.logger.warning(
                    f"Cannot handle dynamic file name on {self.task.action} yet!"
                )
                return abort_result

            if args:
                # Still arguments left?
                self.logger.warning(
                    f"Superfluous arguments on include/import {self.CONTENT_TYPE} task!"
                )
                self.logger.debug(args)

            self.logger.debug(included_name)

            with self._load_content(included_name) as included_content:
                if included_content is None:
                    self.logger.error(f"{self.CONTENT_TYPE} not found: {included_name}")
                    return abort_result

                conditional_nodes: Sequence[rep.ControlNode]
                if self.task.when:
                    condition_result = self.extract_condition(predecessors)
                    # Conditional execution leads to new predecessors
                    predecessors = condition_result.next_predecessors
                    # Save so we can conditionally define variables later
                    conditional_nodes = condition_result.added_control_nodes
                else:
                    conditional_nodes = []

                self.warn_remaining_kws()

                self.logger.info(
                    f"Following include of {self.CONTENT_TYPE} {included_name}"
                )
                included_result = self._extract_included_content(
                    included_content, predecessors
                )

            # If there was a condition, make sure to link up any global variables
            # defined in the content to indicate that they're conditionally
            # defined. We also need to add _ALL_ condition nodes as potential
            # next predecessors, not just the last one, since subsequent conditions
            # may be skipped.
            for condition_node in conditional_nodes:
                for added_var in included_result.added_variable_nodes:
                    self.context.graph.add_edge(
                        condition_node, added_var, rep.DEFINED_IF
                    )

            return included_result.add_control_nodes(
                conditional_nodes
            ).add_next_predecessors(conditional_nodes)
