from __future__ import annotations

from typing import TYPE_CHECKING

from collections.abc import Sequence
from dataclasses import dataclass

from scansible.representations import ast

from ... import representation as rep

if TYPE_CHECKING:
    from .environments import EnvironmentType


@dataclass(frozen=True)
class VariableDefinitionRecord:
    """Binding of a variable at any given time."""

    name: str
    revision: int
    #: The initialiser expression, or the constant variable node if this variable is defined with a value (e.g., facts and `register`ed variables).
    value: ast.AnyExpression | rep.Variable
    env_type: EnvironmentType
    #: Data nodes representing conditions under which this variable is defined.
    conditions: Sequence[rep.DataNode]
    #: The location where the variable is defined.
    location: rep.NodeLocation
