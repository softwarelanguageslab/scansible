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
        # Don't link these conditions to any predecessors, these conditions aren't
        # really part of the control flow.
        condition_nodes = self.extract_condition([]).added_control_nodes

        args = dict(self.task.args)
        # `cacheable` is a module parameter, not a fact.
        # TODO: Cacheable facts may have different precedence under certain
        # circumstances.
        args.pop("cacheable", False)

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
        added_vars: list[rep.Variable] = []

        for var_name, value_node in name_to_value.items():
            var_node = self.context.vars.define_fact(
                var_name,
                EnvironmentType.SET_FACTS_REGISTERED,
                args[var_name],
                value_node,
            )
            added_vars.append(var_node)
            for condition_node in condition_nodes:
                self.context.graph.add_edge(condition_node, var_node, rep.DEFINED_IF)

        self.warn_remaining_kws()
        return ExtractionResult([], added_vars, predecessors)

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
                loop_source_var, loop_target_var, rep.DEF_LOOP_ITEM
            )

            loop_node = rep.Loop(
                loop_with=loop_with,
                location=self.context.get_location(self.task.loop) or self.location,
            )
            self.context.graph.add_node(loop_node)
            self.context.graph.add_edge(loop_source_var, loop_node, rep.USE)

            inner_result = self._extract_bare_task(predecessors)

            for av in inner_result.added_variable_nodes:
                self.context.graph.add_edge(loop_node, av, rep.DEF)

            return inner_result
