"""Program Dependence Graph representation."""
from __future__ import annotations

from typing import Any, Iterable, Literal as LiteralT, TYPE_CHECKING

import attrs
from attrs import define, frozen, field, setters
from networkx.classes import MultiDiGraph

from .._utils import type_validator


ValidTypeStr = LiteralT['str', 'bool', 'int', 'float', 'dict', 'list', 'NoneType', 'VaultValue', 'date', 'datetime']


def non_empty_validator(inst: object, attr: attrs.Attribute[str], value: str) -> None:
    assert isinstance(value, str)
    if not value:
        raise ValueError(f'Expected {attr.name} to be non-empty string, got empty string')


@frozen(str=False)
class NodeLocation:
    file: str = field(validator=type_validator())
    line: int = field(validator=type_validator())
    column: int = field(validator=type_validator())
    includer_location: NodeLocation | None = field(validator=type_validator(), default=None)

    def __str__(self) -> str:
        base = f'{self.file}:{self.line}:{self.column}'
        if self.includer_location:
            base += f'\n\tvia {self.includer_location}'

        return base


def _frozen_node_id(inst: Node, attr: attrs.Attribute[int], new_value: int) -> int:
    if getattr(inst, attr.name) >= 0:
        raise attrs.exceptions.FrozenAttributeError()
    return new_value


@define(slots=False, hash=False)
class Node:
    """Base nodes."""
    node_id: int = field(validator=type_validator(), default=-1, init=False, on_setattr=_frozen_node_id)
    location: NodeLocation | None = field(validator=type_validator(), default=None, kw_only=True, on_setattr=setters.frozen)

    def __hash__(self) -> int:
        if self.node_id is None or self.node_id < 0:
            raise ValueError(f'attempting to hash a partially initialised {self.__class__.__name__}')

        return hash(tuple(getattr(self, attr.name) for attr in self.__attrs_attrs__))  # type: ignore[attr-defined]


@define(slots=False, hash=False)
class ControlNode(Node):
    ...


@define(slots=False, hash=False)
class DataNode(Node):
    ...


@define(slots=False, hash=False)
class Task(ControlNode):
    """Node representing a task."""
    action: str = field(validator=[type_validator(), non_empty_validator], on_setattr=setters.frozen)
    name: str | None = field(validator=type_validator(), on_setattr=setters.frozen, default=None)


class Loop(ControlNode):
    """Node representing start of loop."""


class Conditional(ControlNode):
    """Node representing a condition."""


@define(slots=False, hash=False)
class Variable(DataNode):
    """Node representing variables."""
    name: str = field(validator=[type_validator(), non_empty_validator], on_setattr=setters.frozen)
    version: int = field(validator=type_validator(), on_setattr=setters.frozen)
    value_version: int = field(validator=type_validator(), on_setattr=setters.frozen)
    scope_level: int = field(validator=type_validator(), on_setattr=setters.frozen)


@define(slots=False, hash=False)
class IntermediateValue(DataNode):
    """Node representing intermediate values."""
    identifier: int = field(validator=type_validator(), on_setattr=setters.frozen)


@define(slots=False, hash=False)
class Literal(DataNode):
    """Node representing a literal."""
    type: ValidTypeStr = field(validator=type_validator(), on_setattr=setters.frozen)
    value: Any = field(validator=type_validator(), on_setattr=setters.frozen)


def _convert_to_tuple(obj: tuple[str, ...] | list[str]) -> tuple[str, ...]:
    if isinstance(obj, tuple):
        return obj
    return tuple(obj)


@define(slots=False, hash=False)
class Expression(DataNode):
    """Node representing a template expression."""
    expr: str = field(validator=[type_validator(), non_empty_validator], on_setattr=setters.frozen)

    non_idempotent_components: tuple[str, ...] = field(validator=type_validator(), factory=tuple, converter=_convert_to_tuple, on_setattr=setters.frozen)

    @property
    def idempotent(self) -> bool:
        return not self.non_idempotent_components



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


@frozen
class Order(ControlFlowEdge):
    """Edges representing order between control nodes."""
    transitive: bool = field(validator=type_validator(), default=False)
    back: bool = field(validator=type_validator(), default=False)


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


@frozen
class Keyword(Use):
    """Edges representing data usage as a task keyword."""
    keyword: str = field(validator=type_validator())

    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, DataNode):
            raise TypeError('Keyword edge must start at a data node')

        if not isinstance(target, Task):
            raise TypeError('Keyword edges must only be used with tasks as target')


class Def(DataFlowEdge):
    """Edges representing data definitions."""
    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(target, (Variable, IntermediateValue)):
            raise TypeError('Def edges can only define variables')


class DefinedIf(DataFlowEdge):
    """Edges representing conditional definitions."""
    @classmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(target, Variable):
            raise TypeError('DefinedIf edges can only target variables')
        if not isinstance(source, Conditional):
            raise TypeError('DefinedIf edges must originate from conditionals')


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
DEFINED_IF = DefinedIf()


if TYPE_CHECKING:
    BaseGraph = MultiDiGraph[Node, str, Edge]
else:
    BaseGraph = MultiDiGraph


class Graph(BaseGraph):

    def __init__(self, role_name: str, role_version: str) -> None:
        super().__init__(role_name=role_name, role_version=role_version)
        self._last_node_id = -1

    def _get_next_node_id(self) -> int:
        self._last_node_id += 1
        return self._last_node_id

    @property
    def role_name(self) -> str:
        return self.graph['role_name']

    @property
    def role_version(self) -> str:
        return self.graph['role_version']

    def add_node(self, node: Node) -> None:  # type: ignore[override]
        if not isinstance(node, Node):
            raise TypeError('Can only add Nodes to the graph')

        if node.node_id < 0:
            node.node_id = self._get_next_node_id()
        super().add_node(node)

    def add_nodes_from(self, nodes: Iterable[Node]) -> None:  # type: ignore[override]
        # Adding one-by-one to reuse the checks above
        for node in nodes:
            self.add_node(node)

    def add_edge(self, n1: Node, n2: Node, type: Edge) -> int:  # type: ignore[override]
        type.raise_if_disallowed(n1, n2)
        if n1 not in self or n2 not in self:
            raise ValueError('Both nodes must already be added to the graph')

        existing_edges = self.get_edge_data(n1, n2)
        for edge_idx, edge_data in (existing_edges or {}).items():
            if edge_data['type'] == type:
                return edge_idx

        return super().add_edge(n1, n2, type=type)


__all__ = [
    'Graph',
    'Node', 'ControlNode', 'DataNode', 'Loop', 'Conditional', 'Task', 'Variable', 'Expression', 'IntermediateValue', 'Literal',
    'Edge', 'DEF', 'DEFINED_IF', 'USE', 'ORDER', 'ORDER_TRANS', 'ORDER_BACK', 'Keyword',
    'NodeLocation',
]
