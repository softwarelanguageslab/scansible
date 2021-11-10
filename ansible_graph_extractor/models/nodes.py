"""Graph nodes."""
from typing import Annotated, Any, ClassVar, Literal as LiteralT, Optional

from pydantic import BaseModel, Field, constr


ValidTypeStr = LiteralT['str', 'bool', 'int', 'float', 'dict', 'list', 'NoneType']


class FrozenBase(BaseModel):

    class Config:
        frozen = True


class Node(FrozenBase):
    """Base nodes."""
    # TODO: This shouldn't be shared across all graphs, otherwise we may run
    # into overflows.
    # _next_id: ClassVar[int] = 0

    # @classmethod
    # def _get_id(cls) -> int:
    #     warnings.warn('I am still using shared node IDs across all graphs, possible overflows!')
    #     cls._next_id += 1
    #     return cls._next_id - 1

    node_id: int

class ControlNode(Node):
    ...


class DataNode(Node):
    ...


class Task(ControlNode):
    """Node representing a task."""
    action: constr(strict=True, min_length=1)  # type: ignore[valid-type]
    name: Optional[str]


class Loop(ControlNode):
    """Node representing start of loop."""


class Conditional(ControlNode):
    """Node representing a condition."""


class Variable(DataNode):
    """Node representing variables."""
    name: constr(strict=True, min_length=1)  # type: ignore[valid-type]
    version: int
    value_version: int
    scope_level: int


class IntermediateValue(DataNode):
    """Node representing intermediate values."""
    identifier: int


class Literal(DataNode):
    """Node representing a literal."""
    type: ValidTypeStr
    value: Any


class Expression(DataNode):
    """Node representing a template expression."""
    expr: constr(strict=True)  # type: ignore[valid-type]

