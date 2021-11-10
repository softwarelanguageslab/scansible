from __future__ import annotations

from voyager.models.structural.role import RoleVarFile, DefaultVarFile, RoleVariable, DefaultVariable

from .var_context import ScopeLevel
from .context import ExtractionContext

class VariableFileExtractor:

    def __init__(self, context: ExtractionContext, var_file: RoleVarFile | DefaultVarFile) -> None:
        self.context = context
        self.var_file = var_file

    def extract_variables(self, scope_level: ScopeLevel) -> None:
        for var in self.var_file:
            self.extract_variable(var, scope_level)

    def extract_variable(self, variable: RoleVariable | DefaultVariable, scope_level: ScopeLevel) -> None:
        if not isinstance(variable.value, str):
            self.context.graph.errors.append('I am not able to properly handle non-string values yet')
        self.context.vars.register_variable(variable.name, scope_level, expr=variable.value, graph=self.context.graph)
