"""Graph edges."""
from typing import Any

from pydantic import BaseModel

from .nodes import ControlNode, Conditional, DataNode, Expression, Loop, Literal, Node, Task, Variable, IntermediateValue


class Edge:
    """Base edge."""
    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        raise NotImplementedError()


class ControlFlowEdge(Edge):
    """Edges representing control flow."""

    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not (isinstance(source, ControlNode) and isinstance(target, ControlNode)):
            raise TypeError('Control flow edges are only allowed between control nodes')


class DataFlowEdge(Edge):
    """Edges representing data flow."""


class Order(ControlFlowEdge, BaseModel):
    """Edges representing order between control nodes."""
    transitive: bool = False
    back: bool = False

    class Config:
        frozen = True


class Use(DataFlowEdge):
    """Edges representing data usage."""

    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if isinstance(target, (Loop, Conditional)) and isinstance(source, (Variable, IntermediateValue, Literal)):
            return

        if not isinstance(source, Variable):
            raise TypeError(f'Bare use edge must start at a variable, not at {type(source).__name__}')

        if not isinstance(target, Expression):
            raise TypeError('Bare use edges must only be used with expressions as target')


class Keyword(Use, BaseModel):
    """Edges representing data usage as a task keyword."""
    keyword: str

    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, DataNode):
            raise TypeError('Keyword edge must start at a data node')

        if not isinstance(target, Task):
            raise TypeError('Keyword edges must only be used with tasks as target')

    class Config:
        frozen = True


class Def(DataFlowEdge):
    """Edges representing data definitions."""
    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(target, (Variable, IntermediateValue)):
            raise TypeError('Def edges can only define variables')

class DefLoopItem(DataFlowEdge):
    """Edges representing data definitions for single loop items."""
    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(target, (Variable, IntermediateValue)):
            raise TypeError('Def edges can only define variables')


ORDER = Order()
ORDER_TRANS = Order(transitive=True)
ORDER_BACK = Order(back=True)
USE = Use()
DEF = Def()
DEF_LOOP_ITEM = DefLoopItem()
