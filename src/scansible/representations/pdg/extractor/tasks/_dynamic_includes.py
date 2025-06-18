from __future__ import annotations

from typing import ClassVar, ContextManager, Generic, TypeVar

import abc
import re
from collections.abc import Iterable, Sequence
from functools import reduce

from jinja2 import nodes
from loguru import logger

from scansible.representations.pdg.extractor.expressions.simplification import (
    SimplifiedExpression,
)
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
        included_name_pattern: str,
    ) -> set[str]:
        raise NotImplementedError()

    @abc.abstractmethod
    def _file_exists(self, name: str) -> bool:
        raise NotImplementedError()

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.setup_task_vars_scope(self.TASK_VARS_SCOPE_LEVEL):
            result = self._do_extract(predecessors)
            self.warn_remaining_kws()
            return result

    def _do_extract(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        args = dict(self.task.args)

        included_name_expr = self._extract_included_name(args)
        if args:
            # Still arguments left?
            self.logger.warning(
                f"Superfluous arguments on include/import {self.CONTENT_TYPE} task!"
            )
            self.logger.debug(args)

        self.logger.debug(included_name_expr)

        conditional_nodes = self.extract_conditions()
        with self.context.activate_conditions(conditional_nodes):
            self._check_conditions()

            if not included_name_expr or not isinstance(included_name_expr, str):
                self.logger.error("Unknown included file name!")
                included_result = self._create_placeholder_task(
                    included_name_expr, predecessors
                )
            else:
                included_result = self._process_include_expr(
                    included_name_expr, predecessors
                )

            return self._create_result(
                included_result, predecessors, bool(conditional_nodes)
            )

    def _check_conditions(self) -> None:
        pass

    def _load_and_extract_content(
        self, included_name: str, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        with self._load_content(included_name) as included_content:
            if included_content is None:
                self.logger.error(f"{self.CONTENT_TYPE} not found: {included_name}")
                return self._create_placeholder_task(included_name, predecessors)

            self.logger.info(
                f"Following include of {self.CONTENT_TYPE} {included_name}"
            )
            return self._extract_included_content(included_content, predecessors)

    def _create_placeholder_task(
        self, included_name: AnyValue, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        task_node = rep.Task(
            action=self.task.action, name=self.task.name, location=self.location
        )
        included_name_node = self.context.vars.build_expression(included_name)
        self.context.graph.add_node(task_node)
        self.context.graph.add_edge(
            included_name_node, task_node, rep.Keyword(keyword="_raw_params")
        )

        for predecessor in predecessors:
            self.context.graph.add_edge(predecessor, task_node, rep.ORDER)

        return ExtractionResult.single(task_node)

    def _create_result(
        self,
        included_result: ExtractionResult,
        predecessors: Sequence[rep.ControlNode],
        conditional_include: bool,
    ) -> ExtractionResult:
        if conditional_include:
            return included_result.add_next_predecessors(predecessors)
        return included_result

    def _simplify_included_name_asts(self, name_expr: str) -> set[SimplifiedExpression]:
        """Turn expressions into regular expressions for name selection."""
        ast = TemplateExpressionAST.parse(name_expr)
        if ast is None or ast.is_literal():
            return set()

        assert isinstance(ast.ast_root, nodes.Template)
        return simplify_expression(ast.ast_root, self.context.vars)

    def _process_include_expr(
        self, name_expr: str, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        if not self.context.vars.is_template(name_expr):
            # Literal
            return self._process_literal_include(name_expr, predecessors)

        assert isinstance(name_expr, str)
        candidate_asts = self._simplify_included_name_asts(name_expr)
        if not candidate_asts:
            logger.warning(
                f"Expression {name_expr!r} cannot be statically approximated, "
                + f"cannot follow {self.CONTENT_TYPE} inclusion"
            )
            return self._create_placeholder_task(name_expr, predecessors)

        return self._process_include_candidates(name_expr, candidate_asts, predecessors)

    def _process_include_candidates(
        self,
        name_expr: str,
        candidates: set[SimplifiedExpression],
        predecessors: Sequence[rep.ControlNode],
    ) -> ExtractionResult:
        included_names = set(self._find_filename_candidates(candidates))
        if not included_names:
            logger.warning(
                f"Found no matching files for {name_expr!r}, "
                + f"cannot follow {self.CONTENT_TYPE} inclusion"
            )
            return self._create_placeholder_task(name_expr, predecessors)

        inner_results: list[ExtractionResult] = []
        for included_name, extra_conditions in included_names:
            if extra_conditions:
                conditional_nodes = self.extract_conditions(extra_conditions)
            else:
                conditional_nodes = []

            with self.context.activate_conditions(conditional_nodes):
                inner_result = self._load_and_extract_content(
                    included_name, predecessors
                )
                inner_results.append(inner_result)

        return reduce(lambda r1, r2: r1.merge(r2), inner_results)

    def _find_filename_candidates(
        self, candidates: set[SimplifiedExpression]
    ) -> Iterable[tuple[str, Sequence[str]]]:
        # TODO: This may return the same candidate expression for different
        # conditions, leading to the same code path being added multiple times.
        # How should we handle this?
        for expr in candidates:
            if expr.is_literal:
                if self._file_exists(expr.as_literal()):
                    yield expr.as_literal(), expr.conditions
            else:
                pattern = expr.as_regex()
                if _is_too_general_filename_pattern(pattern):
                    continue
                yield from (
                    (cand, expr.conditions)
                    for cand in self._get_filename_candidates(expr.as_regex())
                )

    def _process_literal_include(
        self, name_expr: str, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        return self._load_and_extract_content(name_expr, predecessors)
