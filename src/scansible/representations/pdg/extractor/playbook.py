from __future__ import annotations

from typing import Sequence

from loguru import logger

from scansible.representations.structural import (
    Block,
    Handler,
    Playbook,
    RoleRequirement,
)

from .context import ExtractionContext
from .expressions import ScopeLevel
from .handler_lists import HandlerListExtractor
from .result import ExtractionResult
from .role_dependencies import extract_role_dependency
from .task_lists import TaskListExtractor
from .variables import VariablesExtractor


class PlaybookExtractor:
    def __init__(self, context: ExtractionContext, playbook: Playbook) -> None:
        self.context = context
        self.playbook = playbook

    def extract(self) -> None:
        # TODO: Inventory vars, group vars, etc. Can we determine these?
        # For playbooks, they can be in group_vars and host_vars relative to the playbook root dir.
        # The "all" file (possibly with .yaml/.yml/.json, but not necessarily) contains variables
        # for all hosts, whereas the other files are for specific hosts.

        for play in self.playbook.plays:
            with self.context.vars.enter_scope(
                ScopeLevel.PLAY_VARS
            ), self.context.vars.enter_scope(
                ScopeLevel.PLAY_VARS_PROMPT
            ), self.context.vars.enter_scope(
                ScopeLevel.PLAY_VARS_FILES
            ):
                # Extract variables first. Order doesn't really matter.

                # - Play variables
                VariablesExtractor(self.context, play.vars).extract_variables(
                    ScopeLevel.PLAY_VARS
                )

                # - Play vars_prompt
                # HACK: These prompts don't always use the default, but we're acting as if it's always the default that's used. TODO: Better representation!
                VariablesExtractor(
                    self.context,
                    {prompt.name: prompt.default for prompt in play.vars_prompt},
                ).extract_variables(ScopeLevel.PLAY_VARS_PROMPT)

                # - Play vars_files
                # TODO: Not clear whether this follows Ansible's search mechanism.
                for vars_file_list in play.vars_files:
                    if not vars_file_list:
                        continue

                    # vars_files entries can themselves be lists, works as the first_found lookup.
                    if isinstance(vars_file_list, str):
                        vars_file_list = [vars_file_list]

                    for vars_file in vars_file_list:
                        # TODO: There should be some form of conditional definition in here.
                        with self.context.include_ctx.load_and_enter_var_file(
                            vars_file, self.context.get_location(vars_file)
                        ) as file_content:
                            if file_content is None:
                                continue

                            VariablesExtractor(
                                self.context, file_content.variables
                            ).extract_variables(ScopeLevel.PLAY_VARS_FILES)
                            break
                    else:
                        logger.bind(location=play.location).error(
                            f"Could not load play vars_file {vars_file!r}"  # pyright: ignore
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
                result = TaskListExtractor(self.context, play.pre_tasks).extract_tasks(
                    []
                )
                result = self._extract_handlers(play.handlers, result)
                result = result.chain(self._extract_roles(play.roles, result))
                result = result.chain(
                    TaskListExtractor(self.context, play.tasks).extract_tasks(
                        result.next_predecessors
                    )
                )
                result = self._extract_handlers(play.handlers, result)
                result = result.chain(
                    TaskListExtractor(self.context, play.post_tasks).extract_tasks(
                        result.next_predecessors
                    )
                )
                result = self._extract_handlers(play.handlers, result)

    def _extract_roles(
        self, roles: Sequence[RoleRequirement], result: ExtractionResult
    ) -> ExtractionResult:
        for role_dep in roles:
            result = result.chain(
                extract_role_dependency(
                    self.context, role_dep, result.next_predecessors
                )
            )
        return result

    def _extract_handlers(
        self, handlers: Sequence[Block | Handler], result: ExtractionResult
    ) -> ExtractionResult:
        return result.chain(
            HandlerListExtractor(self.context, handlers).extract_handlers(
                result.next_predecessors
            )
        )
