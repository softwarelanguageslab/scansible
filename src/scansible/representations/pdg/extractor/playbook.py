from __future__ import annotations

from typing import Sequence

from loguru import logger

from scansible.representations.structural import Playbook, RoleRequirement, Block, Handler

from .. import representation as rep
from .context import ExtractionContext
from .result import ExtractionResult
from .task_lists import TaskListExtractor
from .handler_lists import HandlerListExtractor
from .variables import VariablesExtractor
from .var_context import ScopeLevel
from .role_dependencies import extract_role_dependency

class PlaybookExtractor:

    def __init__(self, context: ExtractionContext, playbook: Playbook) -> None:
        self.context = context
        self.playbook = playbook

    def extract(self) -> None:
        # TODO: Inventory vars, group vars, etc. Can we determine these?
        for play in self.playbook.plays:
            with self.context.vars.enter_scope(ScopeLevel.PLAY_VARS):
                VariablesExtractor(self.context, play.vars).extract_variables(ScopeLevel.PLAY_VARS)
                # TODO: vars_files, vars_prompt


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
                result = TaskListExtractor(self.context, play.pre_tasks).extract_tasks([])
                result = self._extract_handlers(play.handlers, result)
                result = result.chain(self._extract_roles(play.roles, result))
                result = result.chain(TaskListExtractor(self.context, play.tasks).extract_tasks(result.next_predecessors))
                result = self._extract_handlers(play.handlers, result)
                result = result.chain(TaskListExtractor(self.context, play.post_tasks).extract_tasks(result.next_predecessors))
                result = self._extract_handlers(play.handlers, result)

    def _extract_roles(self, roles: Sequence[RoleRequirement], result: ExtractionResult) -> ExtractionResult:
        for role_dep in roles:
            result = result.chain(extract_role_dependency(self.context, role_dep, result.next_predecessors))
        return result

    def _extract_handlers(self, handlers: Sequence[Block | Handler], result: ExtractionResult) -> ExtractionResult:
        return result.chain(HandlerListExtractor(
            self.context,
            handlers
        ).extract_handlers(result.next_predecessors))

