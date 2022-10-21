from __future__ import annotations

from voyager.models.structural.role import RoleVarFile, DefaultVarFile, RoleVariable, DefaultVariable

from ansible_graph_extractor.models import nodes as n
from .var_context import ScopeLevel
from .context import ExtractionContext, ExtractionResult

class VariableFileExtractor:

    def __init__(self, context: ExtractionContext, var_file: RoleVarFile | DefaultVarFile, location: str) -> None:
        self.context = context
        self.var_file = var_file
        self.location = location

    def extract_variables(self, scope_level: ScopeLevel) -> ExtractionResult:
        added_vars: list[n.Variable] = []
        for var in self.var_file:
            added_vars.append(self.extract_variable(var, scope_level))
        return ExtractionResult(
            added_control_nodes=[],
            added_variable_nodes=added_vars
        )

    def extract_variable(self, variable: RoleVariable | DefaultVariable, scope_level: ScopeLevel) -> n.Variable:
        if not isinstance(variable.value, str):
            self.context.graph.errors.append('I am not able to properly handle non-string values yet')
        return self.context.vars.register_variable(variable.name, scope_level, expr=variable.value, location=self.location)
