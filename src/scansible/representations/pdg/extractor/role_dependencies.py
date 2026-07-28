from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from scansible.representations import ast

from .. import representation as rep
from .context import ExtractionContext
from .expressions import EnvironmentType
from .result import ExtractionResult


# TODO: Distinguish between public and private role includes.
def extract_role_dependency(
    context: ExtractionContext,
    dep: ast.RoleRequirement,
    predecessors: Sequence[rep.ControlNode],
) -> ExtractionResult:
    with context.vars.enter_scope(EnvironmentType.INCLUDE_PARAMS):
        for var_name, var_init in dep.params.items():
            try:
                var_ident = ast.Identifier.from_object(var_name)
            except ValueError as e:
                # TODO: Change this if we'd ever support `host_vars` access, etc; see `variables.py`
                logger.warning(
                    f"Ignoring variable {var_name!r}: Variable name is not a valid identifier: {e}",
                )
                continue
            _ = context.vars.define_initialised_variable(
                var_ident, EnvironmentType.INCLUDE_PARAMS, var_init
            )

        # TODO: Conditionals
        with context.include_ctx.load_and_enter_role(
            dep.role, context.get_location(dep.role)
        ) as incl_role:
            if not incl_role:
                logger.bind(location=dep.position).error(
                    f"Could not resolve {dep.role!r} to role"
                )
                return ExtractionResult.empty(predecessors)

            from .role import RoleExtractor

            return RoleExtractor(context, incl_role).extract_role(predecessors)
