"""Graph nodes."""
from typing import Annotated, Any, ClassVar, Literal as LiteralT, Optional, TYPE_CHECKING

from pydantic import BaseModel, Field, constr


ValidTypeStr = LiteralT['str', 'bool', 'int', 'float', 'dict', 'list', 'NoneType']


class FrozenBase(BaseModel):

    class Config:
        frozen = True


class Node(FrozenBase):
    """Base nodes."""
    node_id: int

class ControlNode(Node):
    location: str


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


if TYPE_CHECKING:
    class Variable(DataNode):
        name: str
        version: int
        value_version: int
        scope_level: int
        location: str

else:
    class Variable(DataNode):
        """Node representing variables."""
        name: constr(strict=True, min_length=1)
        version: int
        value_version: int
        scope_level: int
        location: str

        def __repr__(self) -> str:
            return f'{self.name}@{self.version}.{self.value_version}'


class IntermediateValue(DataNode):
    """Node representing intermediate values."""
    identifier: int

    def __repr__(self) -> str:
        return f'${self.identifier}'


class Literal(DataNode):
    """Node representing a literal."""
    type: ValidTypeStr
    value: Any


class Expression(DataNode):
    """Node representing a template expression."""
    expr: constr(strict=True)  # type: ignore[valid-type]

    # Should ideally be a list, but we can't easily serialise those
    # Should be newline separated
    non_idempotent_components_str: str = ''

    @property
    def non_idempotent_components(self) -> list[str]:
        return self.non_idempotent_components_str.split('\n')

    @property
    def idempotent(self) -> bool:
        return not self.non_idempotent_components_str

