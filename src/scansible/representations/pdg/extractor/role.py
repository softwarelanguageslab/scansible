from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from scansible.representations.structural import Role, RoleRequirement

from .. import representation as rep
from .context import ExtractionContext
from .result import ExtractionResult
from .task_lists import TaskListExtractor
from .variables import VariablesExtractor
from .var_context import ScopeLevel

class RoleExtractor:

    def __init__(self, context: ExtractionContext, role: Role) -> None:
        self.context = context
        self.role = role

    def extract_role(self, predecessors: Sequence[rep.ControlNode] | None = None) -> ExtractionResult:
        if predecessors is None:
            predecessors = []

        result = ExtractionResult.empty(predecessors)

        # TODO: Do role variables of the current role get loaded before or after the dependencies?
        if self.role.meta_file:
            for dep in self.role.meta_file.metablock.dependencies:
                result = result.chain(self._extract_role_dependency(dep, result.next_predecessors))

        with self.context.vars.enter_scope(ScopeLevel.ROLE_DEFAULTS), self.context.vars.enter_scope(ScopeLevel.ROLE_VARS):
            if (df := self.role.main_defaults_file) is not None:
                df_result = VariablesExtractor(self.context, df.variables).extract_variables(ScopeLevel.ROLE_DEFAULTS)
                result = result.merge(df_result)

            if (vf := self.role.main_vars_file) is not None:
                vf_result = VariablesExtractor(self.context, vf.variables).extract_variables(ScopeLevel.ROLE_VARS)
                result = result.merge(vf_result)

            # Extract handlers first, as they're needed to link to tasks
            if self.role.main_handlers_file is not None:
                self.context.graph.errors.append('I cannot handle handlers yet!')

            if self.role.main_tasks_file is not None:
                # No need to enter the included file here, it should have already
                # happened. 1) This is a root role, in which case it's already
                # entered in the IncludeContext constructor; 2) This is an included
                # role, in which case it's already entered as the role should have
                # been loaded using IncludeContext.load_and_enter_role.
                tf_result = TaskListExtractor(
                    self.context,
                    self.role.main_tasks_file.tasks  # type: ignore[arg-type]
                ).extract_tasks(result.next_predecessors)
                result = result.chain(tf_result)
            else:
                logger.warning('No main task file')

        return result

    def _extract_role_dependency(self, dep: RoleRequirement, predecessors: Sequence[rep.ControlNode]) -> ExtractionResult:
        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            for var_name, var_init in dep.params.items():
                result = self.context.vars.register_variable(var_name, ScopeLevel.INCLUDE_PARAMS, expr=var_init)

            # TODO: Conditionals
            with self.context.include_ctx.load_and_enter_role(dep.role, self.context.get_location(dep.role)) as incl_role:
                if not incl_role:
                    self.context.graph.errors.append(f'Could not resolve {dep.role!r} to role')
                    return ExtractionResult.empty(predecessors)
                return RoleExtractor(self.context, incl_role).extract_role(predecessors)


