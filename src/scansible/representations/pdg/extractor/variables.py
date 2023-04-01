from __future__ import annotations

from collections.abc import Mapping

from scansible.representations import structural as struct

from .. import representation as rep
from .context import ExtractionContext
from .expressions import EnvironmentType
from .result import ExtractionResult


class VariablesExtractor:
    def __init__(
        self, context: ExtractionContext, variables: Mapping[str, struct.AnyValue]
    ) -> None:
        self.context = context
        self.variables = variables

    def extract_variables(self, scope_level: EnvironmentType) -> ExtractionResult:
        added_vars: list[rep.Variable] = []
        for var_name, var_init in self.variables.items():
            var_node = self.context.vars.define_initialised_variable(
                var_name, scope_level, var_init
            )
            added_vars.append(var_node)
        return ExtractionResult([], added_vars, [])
