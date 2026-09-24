from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import abc
from contextlib import contextmanager

from loguru import logger

from ..semantics import EnvironmentType, RecursiveDefinitionError
from ..variables import VariablesBuilder

if TYPE_CHECKING:
    from collections.abc import Generator, Sequence

    # Not exported outside of stub files.
    from loguru import Logger

    from scansible import ast

    from ... import representation as rep
    from ..context import BuildContext
    from ..result import BuildResult

TaskVarsScopeLevel = Literal[EnvironmentType.TASK_VARS, EnvironmentType.INCLUDE_PARAMS]


class TaskBuilder(abc.ABC):
    @classmethod
    def supported_task_attributes(cls) -> frozenset[str]:
        # tags are ignored
        return frozenset(
            {"name", "action", "args", "when", "vars", "loop_with", "tags"}
        )

    def __init__(self, context: BuildContext, task: ast.BaseTask) -> None:
        self.context: BuildContext = context
        self.task: ast.BaseTask = task
        self.location: rep.NodeLocation = context.get_location(task)
        self.logger: Logger = logger.bind(location=task.location)

    @abc.abstractmethod
    def build_task(self, predecessors: Sequence[rep.ControlNode]) -> BuildResult:
        raise NotImplementedError("To be implemented by subclass")

    def build_conditions(
        self, conditions: Sequence[ast.Condition | ast.BoolLiteral] | None = None
    ) -> list[rep.DataNode]:
        if conditions is None:
            conditions = self.task.when

        condition_value_nodes: list[rep.DataNode] = []
        for condition in conditions:
            # Create an IV for each condition and link it to the conditional node.
            try:
                condition_value_node = self.context.expr.build_expression(condition)
            except RecursiveDefinitionError:
                self.logger.exception("Failed to build expression for task condition")
                continue

            condition_value_nodes.append(condition_value_node)

        return condition_value_nodes

    def build_looping_info(
        self,
    ) -> tuple[rep.DataNode, ast.Identifier, ast.StrLiteral | None] | None:
        loop_expr = self.task.loop
        if not loop_expr:
            return None

        try:
            loop_source_var = self.context.expr.build_expression(loop_expr)
        except RecursiveDefinitionError:
            self.logger.exception("Failed to build expression for loop")
            if self.context.include_ctx.lenient:
                return None
            raise

        loop_var_name = self.task.loop_control.loop_var
        for loop_control_k in self.task.loop_control.model_directives_set:
            if loop_control_k != "loop_var":
                self.logger.debug(
                    f"I cannot handle loop_control option {loop_control_k} yet!"
                )

        return loop_source_var, loop_var_name, self.task.loop_with

    @contextmanager
    def setup_task_vars_scope(self, scope_level: TaskVarsScopeLevel) -> Generator[None]:
        # TODO: Revisit this when we re-introduce caching, sometimes the scope may be cached.
        with self.context.vars.enter_scope(scope_level):
            _ = VariablesBuilder(self.context, self.task.vars).build_variables(
                scope_level
            )
            yield

    def warn_remaining_kws(self, action: str = "") -> None:
        for other_kw in self.task.model_directives_set:
            if other_kw not in self.supported_task_attributes():
                self.logger.debug(
                    f"Cannot handle {other_kw} on {action or self.task.action} yet!"
                )
