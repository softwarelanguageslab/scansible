from __future__ import annotations

from typing import Sequence

from loguru import logger

from scansible.representations.structural import Playbook, RoleRequirement

from .. import representation as rep
from .context import ExtractionContext
from .result import ExtractionResult
from .task_lists import TaskListExtractor
from .variables import VariablesExtractor
from .var_context import ScopeLevel
from .role_dependencies import extract_role_dependency

class PlaybookExtractor:

    def __init__(self, context: ExtractionContext, playbook: Playbook) -> None:
        self.context = context
        self.playbook = playbook

    def extract(self) -> None:
        for play in self.playbook.plays:
            with self.context.vars.enter_scope(ScopeLevel.PLAY_VARS):
                VariablesExtractor(self.context, play.vars).extract_variables(ScopeLevel.PLAY_VARS)
                # TODO: vars_files, vars_prompt

                # TODO: Handlers: Once after pre-tasks, once after tasks, once after post-tasks

                result = TaskListExtractor(self.context, play.pre_tasks).extract_tasks([])
                result = result.chain(self._extract_roles(play.roles, result))
                result = result.chain(TaskListExtractor(self.context, play.tasks).extract_tasks(result.next_predecessors))
                result = result.chain(TaskListExtractor(self.context, play.post_tasks).extract_tasks(result.next_predecessors))

    def _extract_roles(self, roles: Sequence[RoleRequirement], result: ExtractionResult) -> ExtractionResult:
        for role_dep in roles:
            result = result.chain(extract_role_dependency(self.context, role_dep, result.next_predecessors))
        return result

