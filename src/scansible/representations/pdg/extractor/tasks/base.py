from __future__ import annotations

from typing import TYPE_CHECKING, Literal

import abc
from collections.abc import Generator, Sequence
from contextlib import contextmanager

from loguru import logger

from scansible.representations.structural import BaseTask
from scansible.representations.structural.ast import LoopControl

from ... import representation as rep
from ..context import ExtractionContext
from ..expressions import EnvironmentType, RecursiveDefinitionError
from ..result import ExtractionResult
from ..variables import VariablesExtractor

if TYPE_CHECKING:
    # Not exported outside of stub files.
    from loguru import Logger

TaskVarsScopeLevel = Literal[EnvironmentType.TASK_VARS, EnvironmentType.INCLUDE_PARAMS]


class TaskExtractor(abc.ABC):
    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:
        # tags are ignored
        return frozenset(
            {"name", "action", "args", "when", "vars", "loop_with", "tags"}
        )

    def __init__(self, context: ExtractionContext, task: BaseTask) -> None:
        self.context: ExtractionContext = context
        self.task: BaseTask = task
        self.location: rep.NodeLocation = context.get_location(task)
        self.logger: Logger = logger.bind(location=task.position)

    @abc.abstractmethod
    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        raise NotImplementedError("To be implemented by subclass")

    def extract_conditions(
        self,
        conditions: Sequence[str | bool] | None = None,
    ) -> list[rep.DataNode]:
        if conditions is None:
            conditions = self.task.when

        condition_value_nodes: list[rep.DataNode] = []
        for condition in conditions:
            # Create an IV for each condition and link it to the conditional node.
            try:
                condition_value_node = self.context.vars.build_condition(condition)
            except RecursiveDefinitionError as e:
                self.logger.error(e)
                continue

            condition_value_nodes.append(condition_value_node)

        return condition_value_nodes

    def extract_looping_info(self) -> tuple[rep.DataNode, str, str | None] | None:
        loop_expr = self.task.loop
        if not loop_expr:
            return None

        try:
            loop_source_var = self.context.vars.build_expression(loop_expr)
        except RecursiveDefinitionError as e:
            self.logger.error(e)
            if self.context.include_ctx.lenient:
                return None
            else:
                raise

        if self.task.loop_control:
            loop_var_name = self.task.loop_control.loop_var or "item"

            for loop_control_k in LoopControl.model_fields:
                if (
                    loop_control_k == "loop_var"
                    or loop_control_k in self.task.loop_control.model_fields_set
                ):
                    continue
                self.logger.warning(
                    f"I cannot handle loop_control option {loop_control_k} yet!"
                )
        else:
            loop_var_name = "item"

        return loop_source_var, loop_var_name, self.task.loop_with

    @contextmanager
    def setup_task_vars_scope(
        self, scope_level: TaskVarsScopeLevel
    ) -> Generator[None, None, None]:
        # TODO: Revisit this when we re-introduce caching, sometimes the scope may be cached.
        with self.context.vars.enter_scope(scope_level):
            _ = VariablesExtractor(self.context, self.task.vars).extract_variables(
                scope_level
            )
            yield

    def warn_remaining_kws(self, action: str = "") -> None:
        for other_kw in BaseTask.model_fields:
            if other_kw not in self.task.model_fields_set:
                # Default
                continue
            if other_kw not in self.SUPPORTED_TASK_ATTRIBUTES() and other_kw not in (
                "raw",
                "location",
                "parent",
            ):
                self.logger.warning(
                    f"Cannot handle {other_kw} on {action or self.task.action} yet!"
                )
