from __future__ import annotations

from scansible.representations.ast import BaseTask
from scansible.utils import actions

from ..context import BuildContext
from .base import TaskBuilder
from .generic import GenericTaskBuilder
from .include_role import IncludeRoleBuilder
from .include_tasks import IncludeTaskBuilder
from .include_vars import IncludeVarsTaskBuilder
from .set_fact import SetFactTaskBuilder


def task_builder_factory(context: BuildContext, task: BaseTask) -> TaskBuilder:
    action = task.action
    if actions.is_set_fact(action):
        return SetFactTaskBuilder(context, task)
    if actions.is_include_vars(action):
        return IncludeVarsTaskBuilder(context, task)
    if actions.is_import_include_tasks(action):
        return IncludeTaskBuilder(context, task)
    if actions.is_import_include_role(action):
        return IncludeRoleBuilder(context, task)

    return GenericTaskBuilder(context, task)
