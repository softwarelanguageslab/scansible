from __future__ import annotations

from typing import ClassVar, ContextManager, Generic, TypeVar

import abc
import re
from collections.abc import Sequence
from functools import reduce

from jinja2 import nodes
from loguru import logger

from scansible.representations.structural.representation import AnyValue

from ... import representation as rep
from ..expressions import EnvironmentType, TemplateExpressionAST, simplify_expression
from ..result import ExtractionResult
from .base import TaskExtractor, TaskVarsScopeLevel

_IncludedContent = TypeVar("_IncludedContent")


def _is_too_general_filename_pattern(pattern: str) -> bool:
    parts = pattern.split(re.escape("."))
    return len(parts) <= 2 and parts[0] in (".+", "(.+)")


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

    @abc.abstractmethod
    def _get_filename_candidates(
        self,
        included_name_candidates: set[str],
    ) -> set[str]:
        raise NotImplementedError()

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.setup_task_vars_scope(self.TASK_VARS_SCOPE_LEVEL):
            return self._do_extract(predecessors)

    def _do_extract(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        args = dict(self.task.args)
        current_predecessors = predecessors

        included_name_expr = self._extract_included_name(args)
        if args:
            # Still arguments left?
            self.logger.warning(
                f"Superfluous arguments on include/import {self.CONTENT_TYPE} task!"
            )
            self.logger.debug(args)

        self.logger.debug(included_name_expr)

        conditional_nodes: Sequence[rep.ControlNode]
        if self.task.when:
            condition_result = self.extract_condition(predecessors)
            # Conditional execution leads to new predecessors
            predecessors = condition_result.next_predecessors
            # Save so we can conditionally define variables later
            conditional_nodes = condition_result.added_control_nodes
        else:
            conditional_nodes = []

        if not included_name_expr or not isinstance(included_name_expr, str):
            self.logger.error(f"Unknown included file name!")
            included_result = self._create_placeholder_task(
                included_name_expr, predecessors
            )
        else:
            included_result = self._process_include_expr(
                included_name_expr, predecessors
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

    def _build_included_name_patterns(self, name_expr: str) -> set[str]:
        """Turn expressions into regular expressions for name selection."""
        ast = TemplateExpressionAST.parse(name_expr)
        if ast is None or ast.is_literal():
            return {re.escape(name_expr)}

        assert isinstance(ast.ast_root, nodes.Template)
        candidate_asts = simplify_expression(ast.ast_root, self.context.vars)
        patterns = [cand.to_regex() for cand in candidate_asts]
        return {p for p in patterns if not _is_too_general_filename_pattern(p)}

    def _process_include_expr(
        self, name_expr: str, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        included_name_candidates = self._build_included_name_patterns(name_expr)
        if not included_name_candidates:
            logger.warning(
                f"Expression {name_expr!r} cannot be statically approximated, "
                + f"cannot follow {self.CONTENT_TYPE} inclusion"
            )
            return self._create_placeholder_task(name_expr, predecessors)

        included_names = list(self._get_filename_candidates(included_name_candidates))
        if not included_names:
            logger.warning(
                f"Found no matching files for {name_expr!r}, "
                + f"cannot follow {self.CONTENT_TYPE} inclusion"
            )
            return self._create_placeholder_task(name_expr, predecessors)

        inner_results: list[ExtractionResult] = []
        for included_name in included_names:
            inner_results.append(
                self._load_and_extract_content(included_name, predecessors)
            )

        return reduce(lambda r1, r2: r1.merge(r2), inner_results)
