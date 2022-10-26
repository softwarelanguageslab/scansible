from .task import Task
from .base import Value
from .block import Block
from .role import Role
from .task_include import TaskInclude
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from typing import Sequence

class Handler(Task):
    listen: list[str] = ...

    @staticmethod
    def load(data: dict[str, Value], block: Block | None = ..., role: Role | None = ..., task_include: TaskInclude | None = ..., variable_manager: VariableManager | None = ..., loader: DataLoader | None = ...) -> Handler: ...
