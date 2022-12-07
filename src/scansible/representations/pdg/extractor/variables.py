from __future__ import annotations

from collections.abc import Mapping

from loguru import logger

from scansible.representations.structural import VariableFile

from .. import representation as rep
from .var_context import ScopeLevel
from .context import ExtractionContext
from .result import ExtractionResult

class VariablesExtractor:

    def __init__(self, context: ExtractionContext, variables: Mapping[str, object]) -> None:
        self.context = context
        self.variables = variables

    def extract_variables(self, scope_level: ScopeLevel) -> ExtractionResult:
        added_vars: list[rep.Variable] = []
        for var_name, var_init in self.variables.items():
            added_vars.append(self.extract_variable(var_name, var_init, scope_level))
        return ExtractionResult([], added_vars, [])

    def extract_variable(self, var_name: str, var_init: object, scope_level: ScopeLevel) -> rep.Variable:
        if not isinstance(var_init, (str, bool, int, float)):
            logger.warning('I am not able to properly handle non-atomic values yet')
        return self.context.vars.register_variable(var_name, scope_level, expr=var_init)
