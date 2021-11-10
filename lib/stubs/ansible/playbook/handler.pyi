from ansible.playbook.task import Task as Task
from typing import Sequence

class Handler(Task):
    listen: Sequence[str] = ...