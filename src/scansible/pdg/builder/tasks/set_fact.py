from __future__ import annotations

from typing import TYPE_CHECKING, final, override

from scansible import ast

from ... import representation as rep
from ..result import BuildResult
from ..semantics import EnvironmentType, RecursiveDefinitionError
from .base import TaskBuilder

if TYPE_CHECKING:
    from collections.abc import Sequence


@final
class SetFactTaskBuilder(TaskBuilder):
    @classmethod
    @override
    def supported_task_attributes(cls) -> frozenset[str]:
        return super().supported_task_attributes().union({"loop", "loop_control"})

    @override
    def build_task(self, predecessors: Sequence[rep.ControlNode]) -> BuildResult:
        with self.setup_task_vars_scope(EnvironmentType.TASK_VARS):
            if self.task.loop:
                return self._build_looping_task(predecessors)
            return self._build_bare_task(predecessors)

    def _build_bare_task(self, predecessors: Sequence[rep.ControlNode]) -> BuildResult:
        args = dict(self.task.args)
        # `cacheable` is a module parameter, not a fact.
        # TODO: Cacheable facts may have different precedence under certain
        # circumstances.
        _ = args.pop(ast.StrLiteral("cacheable"), False)

        conditions = self.build_conditions()
        with self.context.activate_conditions(conditions):
            # Evaluate all values before defining the variables. Ansible does
            # the same. We need to do this as one variable may be defined in
            # terms of another variable that's `set_fact`ed
            name_to_value: dict[ast.StrLiteral, rep.DataNode] = {}
            for var_name, var_value in args.items():
                try:
                    name_to_value[var_name] = self.context.expr.build_expression(
                        var_value
                    )
                except RecursiveDefinitionError:
                    self.logger.exception(
                        f"Failed to build expression for variable {var_name!r}"
                    )
                    continue

            for var_name, value_node in name_to_value.items():
                var_node = self.context.vars.define_eager_variable(
                    var_name,
                    EnvironmentType.SET_FACTS_REGISTERED,
                    conditions=self.context.active_conditions,
                )
                self.context.graph.add_edge(value_node, var_node, rep.DEF)

        self.warn_remaining_kws()
        return BuildResult.empty(predecessors)

    def _build_looping_task(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> BuildResult:
        source_and_name = self.build_looping_info()
        assert source_and_name is not None, "Internal error"

        loop_source_var, loop_var_name, loop_with = source_and_name
        with self.context.vars.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.define_eager_variable(
                loop_var_name, EnvironmentType.INCLUDE_PARAMS
            )
            self.context.graph.add_edge(
                loop_source_var, loop_target_var, rep.DefLoopItem(loop_with=loop_with)
            )

            with self.context.activate_loop(loop_source_var):
                return self._build_bare_task(predecessors)
