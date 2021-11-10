from ansible.playbook.base import Base
from ansible.playbook.play import Play
from ansible.playbook.collectionsearch import CollectionSearch
from ansible.playbook.conditional import Conditional
from ansible.playbook.taggable import Taggable
from ansible.vars.manager import VariableManager
from ansible.parsing.dataloader import DataLoader
from typing import Mapping, Optional, Union

__metaclass__ = type

class RoleDefinition(Base, Conditional, Taggable, CollectionSearch):
    role: str = ...
    @staticmethod
    def load(data: Union[str, Mapping[object, object]], variable_manager: Optional[VariableManager] = ..., loader: Optional[DataLoader] = ...) -> None: ...
    def get_role_params(self) -> Mapping[str, object]: ...
    def get_role_path(self) -> str: ...
    def get_name(self, include_role_fqcn: bool = ...) -> str: ...
