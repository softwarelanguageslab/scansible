from __future__ import annotations

from typing import TYPE_CHECKING, final

from loguru import logger

from scansible import ast

from .handler_lists import HandlerListBuilder
from .role_dependencies import build_role_dependency
from .semantics import EnvironmentType
from .task_lists import TaskListBuilder
from .variables import VariablesBuilder

if TYPE_CHECKING:
    from collections.abc import Sequence

    from .context import BuildContext
    from .result import BuildResult


@final
class PlaybookBuilder:
    def __init__(self, context: BuildContext, playbook: ast.Playbook) -> None:
        self.context = context
        self.playbook = playbook

    def build(self) -> None:
        # TODO: Inventory vars, group vars, etc. Can we determine these?
        # For playbooks, they can be in group_vars and host_vars relative to the playbook root dir.
        # The "all" file (possibly with .yaml/.yml/.json, but not necessarily) contains variables
        # for all hosts, whereas the other files are for specific hosts.

        for play in self.playbook.plays:
            if not isinstance(play, ast.Play):
                # Skip ImportPlaybook
                continue

            with (
                self.context.vars.enter_scope(EnvironmentType.PLAY_VARS),
                self.context.vars.enter_scope(EnvironmentType.PLAY_VARS_PROMPT),
                self.context.vars.enter_scope(EnvironmentType.PLAY_VARS_FILES),
            ):
                # Build variables first. Order doesn't really matter.

                # - Play variables
                _ = VariablesBuilder(self.context, play.vars).build_variables(
                    EnvironmentType.PLAY_VARS
                )

                # - Play vars_prompt
                # HACK: These prompts don't always use the default, but we're acting as if it's always the default that's used. TODO: Better representation!
                _ = VariablesBuilder(
                    self.context,
                    ast.MapLiteral(
                        (prompt.name, prompt.default) for prompt in play.vars_prompt
                    ),
                ).build_variables(EnvironmentType.PLAY_VARS_PROMPT)

                # - Play vars_files
                # TODO: Not clear whether this follows Ansible's search mechanism.
                for vars_file_list in play.vars_files:
                    if not vars_file_list:
                        continue

                    # vars_files entries can themselves be lists, works as the first_found lookup.
                    resolved_vars_file_list = (
                        [vars_file_list]
                        if isinstance(vars_file_list, str)
                        else vars_file_list
                    )

                    for vars_file in resolved_vars_file_list:
                        # TODO: There should be some form of conditional definition in here.
                        with self.context.include_ctx.load_and_enter_var_file(
                            vars_file, self.context.get_location(vars_file)
                        ) as file_content:
                            if file_content is None:
                                continue

                            _ = VariablesBuilder(
                                self.context, file_content.variables
                            ).build_variables(EnvironmentType.PLAY_VARS_FILES)
                            break
                    else:
                        logger.bind(location=play.location).error(
                            f"Could not load play vars_file {vars_file!r}"  # pyright: ignore[reportPossiblyUnboundVariable]
                        )

                # Follow Ansible's execution order:
                # - pre-tasks
                # - handlers notified by pre-tasks
                # - roles
                # - tasks
                # - handlers notified by tasks
                # - post-tasks
                # - handlers notified by post-tasks

                # TODO: We can perhaps determine which handlers may be notified
                # by each pre-tasks/tasks/post-tasks, and only include those.

                # TODO: It may be possible to notify a role handlers from within
                # a play.
                result = TaskListBuilder(self.context, play.pre_tasks).build_tasks([])
                result = self._build_handlers(play.handlers, result)
                result = result.chain(self._build_roles(play.roles, result))
                result = result.chain(
                    TaskListBuilder(self.context, play.tasks).build_tasks(
                        result.next_predecessors
                    )
                )
                result = self._build_handlers(play.handlers, result)
                result = result.chain(
                    TaskListBuilder(self.context, play.post_tasks).build_tasks(
                        result.next_predecessors
                    )
                )
                result = self._build_handlers(play.handlers, result)

    def _build_roles(
        self, roles: Sequence[ast.RoleRequirement], result: BuildResult
    ) -> BuildResult:
        for role_dep in roles:
            result = result.chain(
                build_role_dependency(self.context, role_dep, result.next_predecessors)
            )
        return result

    def _build_handlers(
        self,
        handlers: Sequence[ast.Handler | ast.HandlerBlock],
        result: BuildResult,
    ) -> BuildResult:
        return result.chain(
            HandlerListBuilder(self.context, handlers).build_handlers(
                result.next_predecessors
            )
        )
