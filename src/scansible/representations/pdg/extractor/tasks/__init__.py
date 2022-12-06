from __future__ import annotations

from ansible import constants as ansible_constants

from scansible.representations.structural import TaskBase

from ..context import ExtractionContext
from .base import TaskExtractor
from .generic import GenericTaskExtractor
from .set_fact import SetFactTaskExtractor
from .include_role import IncludeRoleExtractor
from .include_tasks import IncludeTaskExtractor
from .include_vars import IncludeVarsTaskExtractor


def task_extractor_factory(context: ExtractionContext, task: TaskBase) -> TaskExtractor:
    action = task.action
    if action in ansible_constants._ACTION_SET_FACT:
        return SetFactTaskExtractor(context, task)
    if action in ansible_constants._ACTION_INCLUDE_VARS:
        return IncludeVarsTaskExtractor(context, task)
    if action in ansible_constants._ACTION_ALL_INCLUDE_IMPORT_TASKS:
        return IncludeTaskExtractor(context, task)
    if action in ansible_constants._ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES:
        return IncludeRoleExtractor(context, task)

    return GenericTaskExtractor(context, task)









