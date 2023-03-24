from __future__ import annotations

from collections.abc import Sequence

from loguru import logger

from scansible.representations.structural import Role

from .. import representation as rep
from .context import ExtractionContext
from .expressions import EnvironmentType
from .handler_lists import HandlerListExtractor
from .result import ExtractionResult
from .role_dependencies import extract_role_dependency
from .task_lists import TaskListExtractor
from .variables import VariablesExtractor


class RoleExtractor:
    def __init__(self, context: ExtractionContext, role: Role) -> None:
        self.context = context
        self.role = role

    def extract_role(
        self, predecessors: Sequence[rep.ControlNode] | None = None
    ) -> ExtractionResult:
        if predecessors is None:
            predecessors = []

        result = ExtractionResult.empty(predecessors)

        # TODO: Do role variables of the current role get loaded before or after the dependencies?
        if (mf := self.role.meta_file) is not None:
            with self.context.include_ctx.enter_role_file(mf.file_path):
                for dep in mf.metablock.dependencies:
                    result = result.chain(
                        extract_role_dependency(
                            self.context, dep, result.next_predecessors
                        )
                    )

        with self.context.vars.enter_scope(
            EnvironmentType.ROLE_DEFAULTS
        ), self.context.vars.enter_scope(EnvironmentType.ROLE_VARS):
            if (df := self.role.main_defaults_file) is not None:
                with self.context.include_ctx.enter_role_file(df.file_path):
                    df_result = VariablesExtractor(
                        self.context, df.variables
                    ).extract_variables(EnvironmentType.ROLE_DEFAULTS)
                    result = result.merge(df_result)

            if (vf := self.role.main_vars_file) is not None:
                with self.context.include_ctx.enter_role_file(vf.file_path):
                    vf_result = VariablesExtractor(
                        self.context, vf.variables
                    ).extract_variables(EnvironmentType.ROLE_VARS)
                    result = result.merge(vf_result)

            if self.role.main_tasks_file is not None:
                # No need to enter the included file here, it should have already
                # happened. 1) This is a root role, in which case it's already
                # entered in the IncludeContext constructor; 2) This is an included
                # role, in which case it's already entered as the role should have
                # been loaded using IncludeContext.load_and_enter_role.
                tf_result = TaskListExtractor(
                    self.context,
                    self.role.main_tasks_file.tasks,  # type: ignore[arg-type]
                ).extract_tasks(result.next_predecessors)
                result = result.chain(tf_result)
            else:
                logger.warning("No main task file")

            # TODO: These should somehow be linked to tasks.
            if (hf := self.role.main_handlers_file) is not None:
                with self.context.include_ctx.enter_role_file(hf.file_path):
                    result = result.chain(
                        HandlerListExtractor(
                            self.context, hf.tasks  # type: ignore[arg-type]
                        ).extract_handlers(result.next_predecessors)
                    )

        return result
