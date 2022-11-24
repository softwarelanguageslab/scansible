from __future__ import annotations

from loguru import logger

from scansible.representations.structural import Role, RoleRequirement

from .. import representation as rep
from .context import ExtractionContext, TaskExtractionResult
from .task_lists import TaskListExtractor
from .variables import VariablesExtractor
from .var_context import ScopeLevel

class RoleExtractor:

    def __init__(self, context: ExtractionContext, role: Role) -> None:
        self.context = context
        self.role = role

    def extract_role(self, predecessors: list[rep.ControlNode] | None = None) -> TaskExtractionResult:
        if predecessors is None:
            predecessors = []

        added_control_nodes = []
        added_variable_nodes = []
        next_predecessors = predecessors

        # TODO: Do role variables of the current role get loaded before or after the dependencies?
        if self.role.meta_file:
            for dep in self.role.meta_file.metablock.dependencies:
                dep_result = self._extract_role_dependency(dep, next_predecessors)
                next_predecessors = dep_result.next_predecessors
                added_control_nodes.extend(dep_result.added_control_nodes)
                added_variable_nodes.extend(dep_result.added_variable_nodes)

        with self.context.vars.enter_scope(ScopeLevel.ROLE_DEFAULTS), self.context.vars.enter_scope(ScopeLevel.ROLE_VARS):
            if (df := self.role.main_defaults_file) is not None:
                df_result = VariablesExtractor(self.context, df.variables).extract_variables(ScopeLevel.ROLE_DEFAULTS)
                added_variable_nodes.extend(df_result.added_variable_nodes)

            if (vf := self.role.main_vars_file) is not None:
                vf_result = VariablesExtractor(self.context, vf.variables).extract_variables(ScopeLevel.ROLE_VARS)
                added_variable_nodes.extend(vf_result.added_variable_nodes)

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
                ).extract_tasks(next_predecessors)
                next_predecessors = tf_result.next_predecessors
                added_control_nodes.extend(tf_result.added_control_nodes)
                added_variable_nodes.extend(tf_result.added_variable_nodes)
            else:
                logger.warning('No main task file')

        return TaskExtractionResult(
                added_control_nodes=added_control_nodes,
                added_variable_nodes=added_variable_nodes,
                next_predecessors=next_predecessors)

    def _extract_role_dependency(self, dep: RoleRequirement, predecessors: list[rep.ControlNode]) -> TaskExtractionResult:
        added_variable_nodes = []

        with self.context.vars.enter_scope(ScopeLevel.INCLUDE_PARAMS):
            for var_name, var_init in dep.params.items():
                result = self.context.vars.register_variable(var_name, ScopeLevel.INCLUDE_PARAMS, expr=var_init)
                added_variable_nodes.append(result)

            # TODO: Conditionals
            with self.context.include_ctx.load_and_enter_role(dep.role, self.context.get_location(dep.role)) as incl_role:
                if not incl_role:
                    self.context.graph.errors.append(f'Could not resolve {dep.role!r} to role')
                    return TaskExtractionResult([], added_variable_nodes, predecessors)
                role_result = RoleExtractor(self.context, incl_role).extract_role(predecessors)

                return TaskExtractionResult(role_result.added_control_nodes, role_result.added_variable_nodes + added_variable_nodes, role_result.next_predecessors)


