"""Facilitate access to Ansible playbook types."""
from typing import TYPE_CHECKING

from ansible.playbook.block import Block
from ansible.playbook.handler import Handler
from ansible.playbook.handler_task_include import HandlerTaskInclude
from ansible.playbook.play import Play
from ansible.playbook.task import Task
from ansible.playbook.task_include import TaskInclude

from ansible.parsing.dataloader import DataLoader
from ansible.parsing.mod_args import ModuleArgsParser
from ansible import constants as C
from ansible.errors import AnsibleError

if TYPE_CHECKING:
    # This alias doesn't exist outside of the stub files
    from ansible.playbook.base import Value as AnsibleValue
