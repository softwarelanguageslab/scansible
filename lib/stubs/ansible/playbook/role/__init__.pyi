from __future__ import annotations

from typing import Mapping, Optional, Sequence

from ansible.parsing.dataloader import DataLoader
from ansible.parsing.yaml.objects import AnsibleBaseYAMLObject
from ansible.playbook.base import Base, Value
from ansible.playbook.block import Block
from ansible.playbook.collectionsearch import CollectionSearch
from ansible.playbook.conditional import Conditional
from ansible.playbook.play import Play
from ansible.playbook.role.include import RoleInclude
from ansible.playbook.role.metadata import RoleMetadata
from ansible.playbook.taggable import Taggable
from ansible.vars.manager import VariableManager

from . import definition as definition
from . import include as include
from . import metadata as metadata

class Role(Base, Conditional, Taggable, CollectionSearch):
    @staticmethod
    def load(
        role_include: RoleInclude,
        play: Play,
        parent_role: Optional[Role] = ...,
        from_files: Optional[Mapping[str, object]] = ...,
        from_include: bool = ...,
    ) -> Role: ...
    _role_path: str = ...
    _metadata: RoleMetadata = ...
    _handler_blocks: Sequence[Block] = ...
    _role_vars: Mapping[str, Value] = ...
    _default_vars: Mapping[str, Value] = ...
    _task_blocks: Sequence[Block] = ...
    _play: Play = ...
    _loader: DataLoader = ...
    _variable_manager: VariableManager = ...
    def get_default_vars(
        self, dep_chain: Optional[Sequence[Role]] = ...
    ) -> Mapping[str, Value]: ...
    def get_inherited_vars(
        self, dep_chain: Optional[Sequence[Role]] = ...
    ) -> Mapping[str, Value]: ...
    def get_role_params(
        self, dep_chain: Optional[Sequence[Role]] = ...
    ) -> Mapping[str, object]: ...
    def get_vars(
        self, dep_chain: Optional[Sequence[Role]] = ..., include_params: bool = ...
    ) -> Mapping[str, Value]: ...
    def get_direct_dependencies(self) -> Sequence[Role]: ...
    def get_all_dependencies(self) -> Sequence[Role]: ...
    def get_task_blocks(self) -> Sequence[Block]: ...
    def get_handler_blocks(
        self, play: Play, dep_chain: Optional[Sequence[Role]] = ...
    ) -> Sequence[Block]: ...
    def _load_role_yaml(
        self, subdir: str, main: Optional[str] = ..., allow_dir: bool = ...
    ) -> Optional[AnsibleBaseYAMLObject]: ...
