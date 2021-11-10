from ansible.playbook.role.definition import RoleDefinition
from ansible.playbook.play import Play
from ansible.playbook.role import Role
from ansible.vars.manager import VariableManager
from ansible.parsing.dataloader import DataLoader
from typing import Mapping, Optional, Union

__metaclass__ = type

class RoleInclude(RoleDefinition):
    delegate_to: str = ...
    delegate_facts: bool = ...
    @staticmethod
    def load(data: Union[str, Mapping[object, object]], play: Play, current_role_path: Optional[str] = ..., parent_role: Optional[Role] = ..., variable_manager: Optional[VariableManager] = ..., loader: Optional[DataLoader] = ..., collection_list: Optional[object] = ...) -> RoleInclude: ...  # type: ignore[override]
