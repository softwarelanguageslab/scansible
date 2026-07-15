"""Structural model representation for Ansible roles and playbooks."""

# FIXME!!! Source code position information is largely broken due to Pydantic coercing Ansible types (AnsibleUnicode, AnsibleMapping, ...)
# to plain data types (str, dict, ...), losing the custom `ansible_pos` field.

from __future__ import annotations

# Re-export public AST node types.
from . import extractor as extractor
from .common import BrokenFile as BrokenFile
from .common import BrokenTask as BrokenTask
from .common import ExtractionContext as ExtractionContext
from .common import Position as Position
from .extractor import extract_playbook as extract_playbook
from .extractor import extract_role as extract_role
from .nodes import AST as AST
from .nodes import ASTFile as ASTFile
from .nodes import ASTNode as ASTNode
from .nodes import BaseTask as BaseTask
from .nodes import Block as Block
from .nodes import Handler as Handler
from .nodes import HandlerFile as HandlerFile
from .nodes import LoopControl as LoopControl
from .nodes import MetaBlock as MetaBlock
from .nodes import MetaFile as MetaFile
from .nodes import Platform as Platform
from .nodes import Play as Play
from .nodes import Playbook as Playbook
from .nodes import Role as Role
from .nodes import RoleRequirement as RoleRequirement
from .nodes import Task as Task
from .nodes import TaskFile as TaskFile
from .nodes import VariableFile as VariableFile
from .nodes import VarsPrompt as VarsPrompt
