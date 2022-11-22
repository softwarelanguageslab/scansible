from __future__ import annotations

from loguru import logger

from scansible.representations.structural import Role

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
        with self.context.vars.enter_scope(ScopeLevel.ROLE_DEFAULTS), self.context.vars.enter_scope(ScopeLevel.ROLE_VARS):
            if (df := self.role.main_defaults_file) is not None:
                df_result = VariablesExtractor(self.context, df.variables, rep.NodeLocation.fake()).extract_variables(ScopeLevel.ROLE_DEFAULTS)
                added_variable_nodes.extend(df_result.added_variable_nodes)

            if (vf := self.role.main_vars_file) is not None:
                vf_result = VariablesExtractor(self.context, vf.variables, rep.NodeLocation.fake()).extract_variables(ScopeLevel.ROLE_VARS)
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
                ).extract_tasks(predecessors)
                next_predecessors = tf_result.next_predecessors
                added_control_nodes.extend(tf_result.added_control_nodes)
                added_variable_nodes.extend(tf_result.added_variable_nodes)
            else:
                logger.warning('No main task file')

        return TaskExtractionResult(
                added_control_nodes=added_control_nodes,
                added_variable_nodes=added_variable_nodes,
                next_predecessors=next_predecessors)
