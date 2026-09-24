from __future__ import annotations

from typing import TYPE_CHECKING, final

from loguru import logger

from scansible import ast

from .result import BuildResult

if TYPE_CHECKING:
    from .context import BuildContext
    from .semantics import EnvironmentType


@final
class VariablesBuilder:
    def __init__(
        self,
        context: BuildContext,
        variables: (
            ast.MapLiteral[ast.Identifier, ast.AnyExpression]
            | ast.MapLiteral[ast.ScalarLiteral, ast.AnyExpression]
        ),
    ) -> None:
        self.context = context
        self.variables = variables

    def build_variables(self, scope_level: EnvironmentType) -> BuildResult:
        for var_name, var_init in self.variables.items():
            try:
                var_ident = ast.Identifier.from_object(var_name)
            except ValueError as e:
                # The variable name is not a valid identifier. This can happen in edge cases, e.g.,
                # role variable files allow variable names to be non-strings. However, such invalid
                # names cannot be accessed through a standard variable dereference but can be accessed
                # via vars dictionaries (e.g., `host_vars`). Since we do not handle such variable
                # accesses yet, it's safe to ignore non-string variable names as they'd effectively
                # never be reachable in the AST.
                # TODO: Change this if we'd ever support `host_vars` access, etc.
                logger.warning(
                    f"Ignoring variable {var_name!r}: Variable name is not a valid identifier: {e}"
                )
                continue
            self.context.vars.define_lazy_variable(
                var_ident,
                scope_level,
                var_init,
                conditions=self.context.active_conditions,
            )
        return BuildResult.empty()
