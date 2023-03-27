from __future__ import annotations

from typing import ClassVar, ContextManager, Generic, TypeVar

import abc
from collections.abc import Sequence

from scansible.representations.structural.representation import AnyValue

from ... import representation as rep
from ..expressions import EnvironmentType
from ..result import ExtractionResult
from .base import TaskExtractor, TaskVarsScopeLevel

_IncludedContent = TypeVar("_IncludedContent")


class DynamicIncludesExtractor(TaskExtractor, abc.ABC, Generic[_IncludedContent]):
    CONTENT_TYPE: ClassVar[str]
    TASK_VARS_SCOPE_LEVEL: ClassVar[TaskVarsScopeLevel] = EnvironmentType.INCLUDE_PARAMS

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
        with self.setup_task_vars_scope(self.TASK_VARS_SCOPE_LEVEL):
            return self._do_extract(predecessors)

    def _do_extract(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        args = dict(self.task.args)
        current_predecessors = predecessors

        included_name = self._extract_included_name(args)
        if args:
            # Still arguments left?
            self.logger.warning(
                f"Superfluous arguments on include/import {self.CONTENT_TYPE} task!"
            )
            self.logger.debug(args)

        self.logger.debug(included_name)

        conditional_nodes: Sequence[rep.ControlNode]
        if self.task.when:
            condition_result = self.extract_condition(predecessors)
            # Conditional execution leads to new predecessors
            predecessors = condition_result.next_predecessors
            # Save so we can conditionally define variables later
            conditional_nodes = condition_result.added_control_nodes
        else:
            conditional_nodes = []

        if not included_name or not isinstance(included_name, str):
            self.logger.error(f"Unknown included file name!")
            included_result = self._create_placeholder_task(included_name, predecessors)
        elif "{{" in included_name:
            # TODO: When we do handle expressions here, we should make sure
            # to check whether these expressions can or cannot use the include
            # parameters. If they cannot, we should extract the included
            # name before registering the variables.
            self.logger.warning(
                f"Cannot handle dynamic file name on {self.task.action} yet!"
            )
            included_result = self._create_placeholder_task(included_name, predecessors)
        else:
            included_result = self._load_and_extract_content(
                included_name, predecessors
            )

        # If there was a condition, make sure to link up any global variables
        # defined in the content to indicate that they're conditionally
        # defined. We also need to add _ALL_ condition nodes as potential
        # next predecessors, not just the last one, since subsequent conditions
        # may be skipped.
        for condition_node in conditional_nodes:
            for added_var in included_result.added_variable_nodes:
                self.context.graph.add_edge(condition_node, added_var, rep.DEFINED_IF)

        return self._create_result(
            included_result, current_predecessors, conditional_nodes
        )

    def _load_and_extract_content(
        self, included_name: str, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        with self._load_content(included_name) as included_content:
            if included_content is None:
                self.logger.error(f"{self.CONTENT_TYPE} not found: {included_name}")
                return self._create_placeholder_task(included_name, predecessors)

            self.warn_remaining_kws()

            self.logger.info(
                f"Following include of {self.CONTENT_TYPE} {included_name}"
            )
            return self._extract_included_content(included_content, predecessors)

    def _create_placeholder_task(
        self, included_name: AnyValue, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        task_node = rep.Task(self.task.action, self.task.name, location=self.location)
        included_name_node = self.context.vars.build_expression(included_name)
        self.context.graph.add_node(task_node)
        self.context.graph.add_edge(included_name_node, task_node, rep.Keyword("arg"))

        for predecessor in predecessors:
            self.context.graph.add_edge(predecessor, task_node, rep.ORDER)

        return ExtractionResult([task_node], [], [task_node])

    def _create_result(
        self,
        included_result: ExtractionResult,
        current_predecessors: Sequence[rep.ControlNode],
        added_conditional_nodes: Sequence[rep.ControlNode],
    ) -> ExtractionResult:
        return included_result.add_control_nodes(
            added_conditional_nodes
        ).add_next_predecessors(added_conditional_nodes)
