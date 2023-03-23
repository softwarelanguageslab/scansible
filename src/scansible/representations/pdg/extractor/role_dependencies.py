from __future__ import annotations

from typing import Sequence

from loguru import logger

from scansible.representations.structural import RoleRequirement

from .. import representation as rep
from .context import ExtractionContext
from .result import ExtractionResult
from .var_context import ScopeLevel


def extract_role_dependency(
    context: ExtractionContext,
    dep: RoleRequirement,
    predecessors: Sequence[rep.ControlNode],
) -> ExtractionResult:
    with context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
        for var_name, var_init in dep.params.items():
            context.vars.register_variable(
                var_name, ScopeLevel.INCLUDE_PARAMS, expr=var_init
            )

        # TODO: Conditionals
        with context.include_ctx.load_and_enter_role(
            dep.role, context.get_location(dep.role)
        ) as incl_role:
            if not incl_role:
                logger.bind(location=dep.location).error(
                    f"Could not resolve {dep.role!r} to role"
                )
                return ExtractionResult.empty(predecessors)

            from .role import RoleExtractor

            return RoleExtractor(context, incl_role).extract_role(predecessors)
