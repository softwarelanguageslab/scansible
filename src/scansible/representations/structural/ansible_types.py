"""Facilitate access to Ansible playbook types."""
from __future__ import annotations

from typing import TYPE_CHECKING

from ansible import constants
from ansible.errors import AnsibleError as AnsibleError
from ansible.errors import AnsibleParserError as AnsibleParserError
from ansible.module_utils.parsing.convert_bool import boolean
from ansible.parsing.dataloader import DataLoader as DataLoader
from ansible.parsing.mod_args import ModuleArgsParser as ModuleArgsParser
from ansible.parsing.yaml.objects import AnsibleBaseYAMLObject as AnsibleBaseYAMLObject
from ansible.parsing.yaml.objects import AnsibleMapping as AnsibleMapping
from ansible.parsing.yaml.objects import AnsibleSequence as AnsibleSequence
from ansible.parsing.yaml.objects import (
    AnsibleVaultEncryptedUnicode as AnsibleVaultEncryptedUnicode,
)
from ansible.playbook.base import FieldAttributeBase as FieldAttributeBase
from ansible.playbook.block import Block as Block
from ansible.playbook.handler import Handler as Handler
from ansible.playbook.handler_task_include import (
    HandlerTaskInclude as HandlerTaskInclude,
)
from ansible.playbook.loop_control import LoopControl as LoopControl
from ansible.playbook.play import Play as Play
from ansible.playbook.playbook_include import PlaybookInclude as PlaybookInclude
from ansible.playbook.role_include import IncludeRole as IncludeRole
from ansible.playbook.task import Task as Task
from ansible.playbook.task_include import TaskInclude as TaskInclude
from ansible.plugins.loader import PluginLoader as PluginLoader
from ansible.template import Templar as Templar
from ansible.vars.manager import VariableManager as VariableManager

if TYPE_CHECKING:
    # This alias doesn't exist outside of the stub files
    from ansible.playbook.base import Value

    AnsibleValue = Value


# Fake class as stand-in for module.
class role:
    from ansible.playbook.role.include import RoleInclude as RoleInclude
    from ansible.playbook.role.requirement import RoleRequirement as RoleRequirement


C = constants
convert_bool = boolean
