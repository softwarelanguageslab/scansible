"""AST node representations."""

from __future__ import annotations

from collections.abc import Sequence

from pydantic import BaseModel

from .._validators import AbsolutePath
from ..common import BrokenFile, BrokenTask

# Re-export public AST node types.
from .base import ASTFile as ASTFile
from .base import ASTNode as ASTNode
from .playbook import Play as Play
from .playbook import Playbook as Playbook
from .playbook import VarsPrompt as VarsPrompt
from .role import Role as Role
from .role_meta import MetaBlock as MetaBlock
from .role_meta import MetaFile as MetaFile
from .role_meta import Platform as Platform
from .role_meta import RoleRequirement as RoleRequirement
from .task import BaseTask as BaseTask
from .task import Block as Block
from .task import Handler as Handler
from .task import HandlerFile as HandlerFile
from .task import LoopControl as LoopControl
from .task import Task as Task
from .task import TaskFile as TaskFile
from .variable import VariableFile as VariableFile


class AST(BaseModel, frozen=True):
    """Represents the AST root of a single role or playbook snapshot."""

    #: The path to the role or playbook. For roles, this points to a directory,
    #: for playbooks, this points to the playbook file.
    path: AbsolutePath
    #: The model root.
    root: Role | Playbook

    #: List of broken files that were omitted in lenient mode. Empty in strict mode.
    broken_files: Sequence[BrokenFile]
    #: List of broken tasks that were omitted in lenient mode. Empty in strict mode.
    broken_tasks: Sequence[BrokenTask]

    @property
    def is_role(self) -> bool:
        """Whether the model represents a role. Mutually exclusive with `is_playbook`."""
        return isinstance(self.root, Role)

    @property
    def is_playbook(self) -> bool:
        """Whether the model represents a playbook. Mutually exclusive with `is_role`."""
        return isinstance(self.root, Playbook)
