from __future__ import annotations

from typing import Mapping, Sequence

from ansible.parsing.yaml.objects import AnsibleUnicode
from ansible.playbook.base import Base, Value
from ansible.playbook.collectionsearch import CollectionSearch
from ansible.playbook.taggable import Taggable

from .block import Block
from .handler import Handler
from .role import Role
from .task import Task

class Play(Base, Taggable, CollectionSearch):
    def __init__(self) -> None: ...

    hosts: list[str]

    handlers: Sequence[Block | Handler] = ...
    pre_tasks: Sequence[Block | Task] = ...
    post_tasks: Sequence[Block | Task] = ...
    tasks: Sequence[Block | Task] = ...

    roles: Sequence[Role] = ...

    vars_prompt: Sequence[Mapping[AnsibleUnicode, Value]]
