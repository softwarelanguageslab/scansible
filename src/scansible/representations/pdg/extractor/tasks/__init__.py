from __future__ import annotations

from scansible.representations.structural import TaskBase
from scansible.utils import actions

from ..context import ExtractionContext
from .base import TaskExtractor
from .generic import GenericTaskExtractor
from .include_role import IncludeRoleExtractor
from .include_tasks import IncludeTaskExtractor
from .include_vars import IncludeVarsTaskExtractor
from .set_fact import SetFactTaskExtractor


def task_extractor_factory(context: ExtractionContext, task: TaskBase) -> TaskExtractor:
    action = task.action
    if actions.is_set_fact(action):
        return SetFactTaskExtractor(context, task)
    if actions.is_include_vars(action):
        return IncludeVarsTaskExtractor(context, task)
    if actions.is_import_include_tasks(action):
        return IncludeTaskExtractor(context, task)
    if actions.is_import_include_role(action):
        return IncludeRoleExtractor(context, task)

    return GenericTaskExtractor(context, task)
