from __future__ import annotations

from collections.abc import Sequence

from ... import representation as rep
from ..result import ExtractionResult
from ..var_context import ScopeLevel
from ..variables import VariablesExtractor
from .base import TaskExtractor

class IncludeVarsTaskExtractor(TaskExtractor):

    def extract_task(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.setup_task_vars_scope(ScopeLevel.TASK_VARS):
            return self._do_extract(predecessors)

    def _do_extract(self, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        args = dict(self.task.args)
        result = ExtractionResult.empty(predecessors)

        incl_name = args.pop('_raw_params', '')
        if not incl_name or not isinstance(incl_name, str):
            self.context.graph.errors.append(f'Unknown included file name!')
            return result

        if args:
            self.context.graph.errors.append(f'Additional arguments on included vars action')

        if '{{' in incl_name:
            # TODO: When we do handle expressions here, we should make sure
            # to check whether these expressions can or cannot use the include
            # parameters. If they cannot, we should extract the included
            # name before registering the variables.
            self.context.graph.errors.append(f'Cannot handle dynamic file name on {self.task.action} yet!')
            return result

        with self.context.include_ctx.load_and_enter_var_file(incl_name, self.location) as varfile:
            if not varfile:
                self.context.graph.errors.append(f'Var file not found: {incl_name}')
                return result

            cond_node = self.extract_conditional_value()
            inner_result = VariablesExtractor(self.context, varfile.variables).extract_variables(ScopeLevel.INCLUDE_VARS)
            if cond_node is not None:
                for added_var in inner_result.added_variable_nodes:
                    self.context.graph.add_edge(cond_node, added_var, rep.DEFINED_IF)

        self.warn_remaining_kws()
        return result.merge(inner_result)
