"""Facilitate access to Ansible playbook types."""
from typing import TYPE_CHECKING

from ansible.playbook.base import FieldAttributeBase
from ansible.playbook.block import Block
from ansible.playbook.handler import Handler
from ansible.playbook.handler_task_include import HandlerTaskInclude
from ansible.playbook.loop_control import LoopControl
from ansible.playbook.play import Play
from ansible.playbook.playbook_include import PlaybookInclude
from ansible.playbook.role_include import IncludeRole
from ansible.playbook.task import Task
from ansible.playbook.task_include import TaskInclude

from ansible.parsing.yaml.objects import AnsibleSequence, AnsibleMapping, AnsibleBaseYAMLObject, AnsibleVaultEncryptedUnicode
from ansible.module_utils.parsing.convert_bool import boolean as convert_bool
from ansible.template import Templar
from ansible.parsing.dataloader import DataLoader
from ansible.vars.manager import VariableManager
from ansible.parsing.mod_args import ModuleArgsParser
from ansible import constants as C
from ansible.errors import AnsibleError, AnsibleParserError

if TYPE_CHECKING:
    # This alias doesn't exist outside of the stub files
    from ansible.playbook.base import Value as AnsibleValue
