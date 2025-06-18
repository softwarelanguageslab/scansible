from __future__ import annotations

from collections.abc import Sequence

from ... import representation as rep
from ..expressions import EnvironmentType, RecursiveDefinitionError
from ..result import ExtractionResult
from .base import TaskExtractor


class SetFactTaskExtractor(TaskExtractor):
    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:
        return super().SUPPORTED_TASK_ATTRIBUTES().union({"loop", "loop_control"})

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.setup_task_vars_scope(EnvironmentType.TASK_VARS):
            if self.task.loop:
                return self._extract_looping_task(predecessors)
            return self._extract_bare_task(predecessors)

    def _extract_bare_task(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        args = dict(self.task.args)
        # `cacheable` is a module parameter, not a fact.
        # TODO: Cacheable facts may have different precedence under certain
        # circumstances.
        args.pop("cacheable", False)

        conditions = self.extract_conditions()

        # Evaluate all values before defining the variables. Ansible does
        # the same. We need to do this as one variable may be defined in
        # terms of another variable that's `set_fact`ed
        name_to_value: dict[str, rep.DataNode] = {}
        for var_name, var_value in args.items():
            try:
                name_to_value[var_name] = self.context.vars.build_expression(var_value)
            except RecursiveDefinitionError as e:
                self.logger.error(e)
                continue

        for var_name, value_node in name_to_value.items():
            var_node = self.context.vars.define_fact(
                var_name,
                EnvironmentType.SET_FACTS_REGISTERED,
                args[var_name],
                value_node,
            )
            with self.context.activate_conditions(conditions):
                for condition_node in self.context.active_conditions:
                    self.context.graph.add_edge(condition_node, var_node, rep.WHEN)

        self.warn_remaining_kws()
        return ExtractionResult.empty(predecessors)

    def _extract_looping_task(
        self, predecessors: Sequence[rep.ControlNode]
    ) -> ExtractionResult:
        source_and_name = self.extract_looping_info()
        assert source_and_name is not None, "Internal error"

        loop_source_var, loop_var_name, loop_with = source_and_name
        with self.context.vars.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.define_injected_variable(
                loop_var_name, EnvironmentType.INCLUDE_PARAMS
            )
            self.context.graph.add_edge(
                loop_source_var, loop_target_var, rep.DefLoopItem(loop_with=loop_with)
            )

            with self.context.activate_loop(loop_source_var):
                return self._extract_bare_task(predecessors)
