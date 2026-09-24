"""AST node representations."""

from __future__ import annotations

from collections.abc import Sequence  # noqa: TC003 -- For Pydantic

from pydantic import BaseModel

from .._validators import AbsolutePath  # noqa: TC001
from ..common import BrokenFile, BrokenTask  # noqa: TC001

# Re-export public AST node types.
from .base import *
from .expression import *
from .playbook import *
from .role import *
from .role_meta import *
from .task import *
from .variable import *


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


# Deliberate duplication as basedpyright otherwise complains about unsupported operations on `__all__`,
# possibly leading to degraded static tooling.
__all__ = [
    "AST",
    # .base
    "ASTFile",
    "ASTNode",
    # .expression
    "Expression",
    "Condition",
    "Identifier",
    "StrLiteral",
    "IntLiteral",
    "FloatLiteral",
    "PercentLiteral",
    "BoolLiteral",
    "DateLiteral",
    "DatetimeLiteral",
    "SeqLiteral",
    "MapLiteral",
    "ScalarLiteral",
    "CompositeLiteral",
    "AnyLiteral",
    "AnyExpression",
    # .playbook
    "VarsPrompt",
    "Play",
    "ImportPlaybook",
    "Playbook",
    # .role
    "Role",
    # .role_meta
    "Platform",
    "RoleRequirement",
    "MetaBlock",
    "MetaFile",
    # .task
    "LoopControl",
    "BaseTask",
    "Task",
    "Handler",
    "BaseBlock",
    "Block",
    "HandlerBlock",
    "TaskFile",
    "HandlerFile",
    # .variable
    "VariableFile",
]
