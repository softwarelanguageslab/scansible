from typing import Sequence, Mapping

from ansible.playbook.base import Base, Value
from ansible.playbook.collectionsearch import CollectionSearch
from ansible.playbook.taggable import Taggable
from ansible.parsing.yaml.objects import AnsibleUnicode

from .block import Block
from .task import Task
from .handler import Handler
from .role import Role

class Play(Base, Taggable, CollectionSearch):
    def __init__(self) -> None: ...

    hosts: list[str]

    handlers: Sequence[Block | Handler] = ...
    pre_tasks: Sequence[Block | Task] = ...
    post_tasks: Sequence[Block | Task] = ...
    tasks: Sequence[Block | Task] = ...

    roles: Sequence[Role] = ...

    vars_prompt: Sequence[Mapping[AnsibleUnicode, Value]]
