from __future__ import annotations

from loguru import logger

from scansible.representations.structural import Playbook

from .. import representation as rep
from .context import ExtractionContext
from .task_lists import TaskListExtractor
from .variables import VariablesExtractor
from .var_context import ScopeLevel

class PlaybookExtractor:

    def __init__(self, context: ExtractionContext, playbook: Playbook) -> None:
        self.context = context
        self.playbook = playbook

    def extract(self) -> None:
        for play in self.playbook.plays:
            with self.context.vars.enter_scope(ScopeLevel.PLAY_VARS):
                VariablesExtractor(self.context, play.vars).extract_variables(ScopeLevel.PLAY_VARS)
                TaskListExtractor(self.context, play.tasks).extract_tasks([])

