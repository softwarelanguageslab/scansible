from ansible.playbook.base import Base
from ansible.playbook.collectionsearch import CollectionSearch
from ansible.playbook.role import Role
from typing import Any, Mapping, Optional, Sequence

from ansible.playbook.base import Value

from .include import RoleInclude

class RoleMetadata(Base, CollectionSearch):
    allow_duplicates: bool = ...
    dependencies: Sequence[RoleInclude] = ...
    galaxy_info: Optional[Mapping[str, Value]] = ...
    owner: Role = ...
