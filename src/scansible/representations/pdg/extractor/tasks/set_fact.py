from __future__ import annotations

from collections.abc import Sequence

from ... import representation as rep
from ..result import ExtractionResult
from ..var_context import ScopeLevel
from .base import TaskExtractor

class SetFactTaskExtractor(TaskExtractor):
    @classmethod
    def SUPPORTED_TASK_ATTRIBUTES(cls) -> frozenset[str]:
        return super().SUPPORTED_TASK_ATTRIBUTES().union({'loop', 'loop_control'})

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.setup_task_vars_scope(ScopeLevel.TASK_VARS):
            if self.task.loop:
                return self._extract_looping_task(predecessors)
            return self._extract_bare_task(predecessors)

    def _extract_bare_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        result = ExtractionResult.empty(predecessors)

        with self.context.vars.enter_cached_scope(ScopeLevel.TASK_VARS):
            # Evaluate all values before defining the variables. Ansible does
            # the same. We need to do this as one variable may be defined in
            # terms of another variable that's `set_fact`ed
            name_to_value = {var_name: self.extract_value(var_value) for var_name, var_value in self.task.args.items()}
            cond_val = self.extract_conditional_value()
            added_vars = []

            for var_name, value_node in name_to_value.items():
                var_node = self.context.vars.register_variable(var_name, ScopeLevel.SET_FACTS_REGISTERED)
                added_vars.append(var_node)

                self.context.graph.add_node(var_node)
                self.context.graph.add_edge(value_node, var_node, rep.DEF)
                if cond_val is not None:
                    self.context.graph.add_edge(cond_val, var_node, rep.DEFINED_IF)

        self.warn_remaining_kws()
        return result.add_variable_nodes(added_vars)

    def _extract_looping_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        self.context.graph.errors.append('loops on set_fact are not fully supported yet')
        source_and_name = self.extract_looping_value_and_name()
        assert source_and_name is not None, 'Internal error'

        loop_source_var, loop_var_name = source_and_name
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            loop_target_var = self.context.vars.register_variable(loop_var_name, ScopeLevel.INCLUDE_PARAMS)
            self.context.graph.add_edge(loop_source_var, loop_target_var, rep.DEF_LOOP_ITEM)

            return self._extract_bare_task(predecessors)
