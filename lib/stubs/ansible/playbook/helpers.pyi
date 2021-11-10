from ansible.parsing.yaml.objects import AnsibleSequence
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager

from typing import Optional, Sequence

from .play import Play
from .block import Block
from .role import Role
from .role.include import RoleInclude
from .task import Task
from .task_include import TaskInclude

def load_list_of_blocks(ds: AnsibleSequence, play: Play, parent_block: Optional[Block] = ..., role: Optional[Role] = ..., task_include: Optional[TaskInclude] = ..., use_handlers: bool = ..., variable_manager: Optional[VariableManager] = ..., loader: Optional[DataLoader] = ...) -> Sequence[Block]: ...
def load_list_of_tasks(ds: AnsibleSequence, play: Play, block: Optional[Block] = ..., role: Optional[Role] = ..., task_include: Optional[TaskInclude] = ..., use_handlers: bool = ..., variable_manager: Optional[VariableManager] = ..., loader: Optional[DataLoader] = ...) -> Sequence[Task]: ...
def load_list_of_roles(ds: AnsibleSequence, play: Play, current_role_path: Optional[str] = ..., variable_manager: Optional[VariableManager] = ..., loader: Optional[DataLoader] = ..., collection_search_list: Optional[Sequence[object]] = ...) -> Sequence[RoleInclude]: ...
