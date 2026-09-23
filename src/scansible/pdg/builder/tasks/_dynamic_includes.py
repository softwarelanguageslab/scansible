from __future__ import annotations

from typing import ClassVar, override

import abc
import re
from collections.abc import Iterable, Sequence
from contextlib import AbstractContextManager
from functools import reduce

from jinja2 import nodes
from loguru import logger

from scansible import ast

from ... import representation as rep
from ..result import BuildResult
from ..semantics.expressions import TemplateExpressionAST, simplify_expression
from ..semantics.expressions.simplification import SimplifiedExpression
from ..semantics.variables import EnvironmentType
from .base import TaskBuilder, TaskVarsScopeLevel


def _is_too_general_filename_pattern(pattern: str) -> bool:
    parts = pattern.split(re.escape("."))
    return len(parts) <= 2 and parts[0] in (".+", "(.+)")


class DynamicIncludesBuilder[Content](TaskBuilder, abc.ABC):
    CONTENT_TYPE: ClassVar[str]
    TASK_VARS_SCOPE_LEVEL: ClassVar[TaskVarsScopeLevel] = EnvironmentType.INCLUDE_PARAMS

    @abc.abstractmethod
    def _extract_included_name(
        self, args: dict[ast.StrLiteral, ast.AnyExpression]
    ) -> ast.AnyExpression:
        """Extract included name from arguments, and pop the argument."""
        raise NotImplementedError

    @abc.abstractmethod
    def _load_content(
        self, included_name: ast.StrLiteral
    ) -> AbstractContextManager[Content | None]:
        """Load and enter included content as a context manager."""
        raise NotImplementedError

    @abc.abstractmethod
    def _build_included_content(
        self, included_content: Content, predecessors: Sequence[rep.ControlNode]
    ) -> BuildResult:
        raise NotImplementedError

    @abc.abstractmethod
    def _get_filename_candidates(self, included_name_pattern: str) -> set[str]:
        raise NotImplementedError

    @abc.abstractmethod
    def _file_exists(self, name: str) -> bool:
        raise NotImplementedError

    @override
    def build_task(self, predecessors: Sequence[rep.ControlNode]) -> BuildResult:
        with self.setup_task_vars_scope(self.TASK_VARS_SCOPE_LEVEL):
            result = self._do_build(predecessors)
            self.warn_remaining_kws()
            return result

    def _do_build(self, predecessors: Sequence[rep.ControlNode]) -> BuildResult:
        args = dict(self.task.args)

        included_name_expr = self._extract_included_name(args)
        if args:
            # Still arguments left?
            self.logger.warning(
                f"Superfluous arguments on include/import {self.CONTENT_TYPE} task!"
            )
            self.logger.debug(args)

        self.logger.debug(included_name_expr)

        conditional_nodes = self.build_conditions()
        with self.context.activate_conditions(conditional_nodes):
            self._check_conditions()

            if not included_name_expr or not isinstance(
                included_name_expr, (ast.StrLiteral, ast.Expression)
            ):
                self.logger.error("Unknown included file name!")
                included_result = self._create_placeholder_task(
                    included_name_expr, predecessors
                )
            else:
                included_result = self._process_include_expr(
                    included_name_expr, predecessors
                )

            if conditional_nodes:
                included_result = included_result.add_next_predecessors(predecessors)

            return included_result

    def _check_conditions(self) -> None:
        pass

    def _load_and_build_content(
        self, included_name: ast.StrLiteral, predecessors: Sequence[rep.ControlNode]
    ) -> BuildResult:
        with self._load_content(included_name) as included_content:
            if included_content is None:
                self.logger.error(f"{self.CONTENT_TYPE} not found: {included_name}")
                return self._create_placeholder_task(included_name, predecessors)

            self.logger.trace(
                f"Following include of {self.CONTENT_TYPE} {included_name}"
            )
            return self._build_included_content(included_content, predecessors)

    def _create_placeholder_task(
        self, included_name: ast.AnyExpression, predecessors: Sequence[rep.ControlNode]
    ) -> BuildResult:
        task_node = rep.Task(
            action=self.task.action, name=self.task.name, location=self.location
        )
        included_name_node = self.context.expr.build_expression(included_name)
        self.context.graph.add_node(task_node)
        self.context.graph.add_edge(
            included_name_node, task_node, rep.Keyword(keyword="_raw_params")
        )

        for predecessor in predecessors:
            self.context.graph.add_edge(predecessor, task_node, rep.ORDER)

        return BuildResult.single(task_node)

    def _simplify_included_name_asts(
        self, name_expr: ast.Expression
    ) -> set[SimplifiedExpression]:
        """Turn expressions into regular expressions for name selection."""
        ast = TemplateExpressionAST(name_expr)
        assert isinstance(ast.ast_root, nodes.Template)
        return simplify_expression(ast.ast_root, self.context.vars)

    def _process_include_expr(
        self,
        name_expr: ast.StrLiteral | ast.Expression,
        predecessors: Sequence[rep.ControlNode],
    ) -> BuildResult:
        if isinstance(name_expr, ast.StrLiteral):
            return self._process_literal_include(name_expr, predecessors)

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
        name_expr: ast.Expression,
        candidates: set[SimplifiedExpression],
        predecessors: Sequence[rep.ControlNode],
    ) -> BuildResult:
        included_names = set(self._find_filename_candidates(candidates))
        if not included_names:
            logger.warning(
                f"Found no matching files for {name_expr!r}, "
                + f"cannot follow {self.CONTENT_TYPE} inclusion"
            )
            return self._create_placeholder_task(name_expr, predecessors)

        inner_results: list[BuildResult] = []
        for included_name, extra_conditions in included_names:
            if extra_conditions:
                conditional_nodes = self.build_conditions(extra_conditions)
            else:
                conditional_nodes = []

            with self.context.activate_conditions(conditional_nodes):
                inner_result = self._load_and_build_content(included_name, predecessors)
                inner_results.append(inner_result)

        return reduce(lambda r1, r2: r1.merge(r2), inner_results)

    def _find_filename_candidates(
        self, candidates: set[SimplifiedExpression]
    ) -> Iterable[tuple[ast.StrLiteral, Sequence[ast.Condition]]]:
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
                    (ast.StrLiteral(cand), expr.conditions)
                    for cand in self._get_filename_candidates(expr.as_regex())
                )

    def _process_literal_include(
        self, name_expr: ast.StrLiteral, predecessors: Sequence[rep.ControlNode]
    ) -> BuildResult:
        return self._load_and_build_content(name_expr, predecessors)
