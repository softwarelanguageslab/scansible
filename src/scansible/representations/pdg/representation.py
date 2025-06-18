"""Program Dependence Graph representation."""

from __future__ import annotations

from typing import TYPE_CHECKING, Annotated, final, overload, override
from typing import Literal as LiteralT

import abc
from collections.abc import Iterable

from networkx.algorithms.dag import transitive_closure
from networkx.classes import MultiDiGraph
from networkx.classes.graphviews import subgraph_view
from pydantic import BaseModel, Field, StringConstraints, field_validator

type ValidTypeStr = LiteralT[
    "str",
    "bool",
    "int",
    "float",
    "dict",
    "list",
    "NoneType",
    "VaultValue",
    "date",
    "datetime",
]

type Scalar = str | int | bool | float | None


class _BaseRepresentation(BaseModel, strict=True, extra="forbid"):
    pass


class _FrozenRepresentation(BaseModel, frozen=True, strict=True, extra="forbid"):
    pass


class NodeLocation(_FrozenRepresentation, frozen=True):
    file: str
    line: int
    column: int
    includer_location: NodeLocation | None = None

    @override
    def __str__(self) -> str:
        base = f"{self.file}:{self.line}:{self.column}"
        if self.includer_location:
            base += f"\n\tvia {self.includer_location}"

        return base


class Node(_BaseRepresentation):
    """Base nodes."""

    # TODO: Prevent reassignment to node_id once instantiated
    node_id: int = Field(init=False, default=-1)
    location: NodeLocation | None = Field(default=None, kw_only=True, frozen=True)

    @override
    def __hash__(self) -> int:
        if self.node_id < 0:
            raise ValueError(
                f"attempting to hash a partially initialised {self.__class__.__name__}"
            )

        return hash(tuple(self))


class ControlNode(Node, _BaseRepresentation): ...


class DataNode(Node, _BaseRepresentation): ...


class Task(ControlNode, _BaseRepresentation):
    """Node representing a task."""

    action: Annotated[str, StringConstraints(min_length=1)] = Field(frozen=True)
    name: str | None = Field(frozen=True, default=None)


class Variable(DataNode, _BaseRepresentation):
    """Node representing variables."""

    name: Annotated[str, StringConstraints(min_length=1)] = Field(frozen=True)
    version: int = Field(frozen=True)
    value_version: int = Field(frozen=True)
    scope_level: int = Field(frozen=True)


class IntermediateValue(DataNode, _BaseRepresentation):
    """Node representing intermediate values."""

    identifier: int = Field(frozen=True)


class Literal(DataNode, _BaseRepresentation):
    """Node representing a literal."""

    type: ValidTypeStr = Field(frozen=True)


class ScalarLiteral(Literal, _BaseRepresentation):
    value: Scalar = Field(frozen=True)


class CompositeLiteral(Literal, _BaseRepresentation):
    """Node representing a literal of a composite type."""


class Expression(DataNode, _BaseRepresentation):
    """Node representing a template expression."""

    expr: Annotated[str, StringConstraints(min_length=1)] = Field(frozen=True)
    is_conditional: bool = Field(frozen=True, default=False)
    orig_expr: str = Field(frozen=True, default="")

    impure_components: tuple[str, ...] = Field(frozen=True, default_factory=tuple)

    @property
    def is_pure(self) -> bool:
        return not self.impure_components

    @field_validator("impure_components", mode="before")
    @classmethod
    def _convert_impure_components_list(cls, value: object) -> object:
        # Needs to be a tuple for hashing, but when deserialising it could be
        # provided as a list (e.g., in the GraphML deserialiser or from JSON).
        if isinstance(value, list):
            return tuple(value)
        return value


class Edge(abc.ABC, _FrozenRepresentation, frozen=True):
    """Base edge."""

    @classmethod
    @abc.abstractmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        raise NotImplementedError()


class ControlFlowEdge(Edge, _FrozenRepresentation, frozen=True):
    """Edges representing control flow."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not (isinstance(source, ControlNode) and isinstance(target, ControlNode)):
            raise TypeError("Control flow edges are only allowed between control nodes")


class DataFlowEdge(Edge, abc.ABC, _FrozenRepresentation, frozen=True):
    """Edges representing data flow."""


class Order(ControlFlowEdge, _FrozenRepresentation, frozen=True):
    """Edges representing order between control nodes."""

    transitive: bool = False
    back: bool = False


class Notifies(ControlFlowEdge, _FrozenRepresentation, frozen=True):
    """Edges representing notification from task to handler."""


class When(ControlFlowEdge, _FrozenRepresentation, frozen=True):
    """Edges representing conditional execution from data node to task."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        # Can end in both data nodes (conditional definition) or control nodes (conditional execution)
        if not isinstance(source, DataNode):
            raise TypeError("Conditional edges are only allowed from data node")


class Loop(ControlFlowEdge, _FrozenRepresentation, frozen=True):
    """Edges representing looping execution from data node (over which we iterate)
    to task."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not (isinstance(source, DataNode) and isinstance(target, ControlNode)):
            raise TypeError(
                "Loop edges are only allowed from data node to control nodes"
            )


class Use(DataFlowEdge, _FrozenRepresentation, frozen=True):
    """Edges representing data usage."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, Variable):
            raise TypeError(
                f"Bare use edge must start at a variable, not at {type(source).__name__}"
            )

        if not isinstance(target, Expression):
            raise TypeError(
                "Bare use edges must only be used with expressions as target"
            )


class Input(Use, _FrozenRepresentation, frozen=True):
    param_idx: int

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, DataNode):
            raise TypeError("Input edge must start at a data node")

        if not isinstance(target, Expression):
            raise TypeError("Input edges must only be used with expressions as target")


class Keyword(Use, _FrozenRepresentation, frozen=True):
    """Edges representing data usage as a task keyword."""

    keyword: str

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, DataNode):
            raise TypeError("Keyword edge must start at a data node")

        if not isinstance(target, Task):
            raise TypeError("Keyword edges must only be used with tasks as target")


class Composition(Use, _FrozenRepresentation, frozen=True):
    """Edges representing data composition in composite values."""

    index: str

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, DataNode):
            raise TypeError("Composition edge must start at a data node")

        if not isinstance(target, CompositeLiteral):
            raise TypeError(
                "Keyword edges must only be used with composite literals as target"
            )


class Def(DataFlowEdge, _FrozenRepresentation, frozen=True):
    """Edges representing data definitions."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(target, DataNode):
            raise TypeError("Def edges can only define data")
        if isinstance(target, Literal):
            raise TypeError("Def edges cannot define literals")


class DefLoopItem(Def, _FrozenRepresentation, frozen=True):
    """Edges representing data definitions for single loop items."""

    loop_with: str | None

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(target, (Variable, IntermediateValue)):
            raise TypeError("Def edges can only define variables")


ORDER = Order()
ORDER_TRANS = Order(transitive=True)
ORDER_BACK = Order(back=True)
NOTIFIES = Notifies()
USE = Use()
DEF = Def()
WHEN = When()
LOOP = Loop()


if TYPE_CHECKING:
    BaseGraph = MultiDiGraph[Node, str, Edge]
else:
    BaseGraph = MultiDiGraph


@final
class Graph(BaseGraph):
    def __init__(self, role_name: str = "", role_version: str = "") -> None:
        super().__init__(role_name=role_name, role_version=role_version)
        self._last_node_id = -1
        self._dirty = False

    def _get_next_node_id(self) -> int:
        self._last_node_id += 1
        return self._last_node_id

    @property
    def role_name(self) -> str:
        return self.graph["role_name"]

    @property
    def role_version(self) -> str:
        return self.graph["role_version"]

    def add_node(self, node: Node) -> None:  # type: ignore[override]
        if not isinstance(node, Node):  # pyright: ignore
            raise TypeError(f"Can only add Nodes to the graph, given {node}")

        if node.node_id < 0:
            node.node_id = self._get_next_node_id()
        self._dirty = True
        super().add_node(node)

    def add_nodes_from(
        self, nodes: Iterable[Node] | Iterable[tuple[Node, dict[str, str]]]
    ) -> None:  # type: ignore[override]
        # Adding one-by-one to reuse the checks above
        for node in nodes:
            if isinstance(node, tuple):
                self.add_node(node[0])
            else:
                self.add_node(node)

    @overload  # type: ignore[override]
    def add_edge(self, n1: Node, n2: Node, type: Edge) -> int: ...

    @overload
    def add_edge(self, n1: Node, n2: Node, *, key: int | None) -> int: ...

    def add_edge(  # type: ignore[misc]  # pyright: ignore
        self,
        n1: Node,
        n2: Node,
        edge_or_key: Edge | int | None,
    ) -> int:
        if edge_or_key is None or isinstance(edge_or_key, int):
            # Original signature, called from add_edges_from
            return super().add_edge(n1, n2, edge_or_key)

        edge = edge_or_key
        edge.raise_if_disallowed(n1, n2)
        if n1 not in self or n2 not in self:
            raise ValueError("Both nodes must already be added to the graph")

        existing_edges = self.get_edge_data(n1, n2)
        for edge_idx, edge_data in (existing_edges or {}).items():
            if edge_data["type"] == edge:
                return edge_idx

        self._dirty = True
        return super().add_edge(n1, n2, type=edge)

    def remove_edge(self, n1: Node, n2: Node, key: int | None = None) -> None:
        self._dirty = True
        return super().remove_edge(n1, n2, key)

    def remove_node(self, node: Node) -> None:
        self._dirty = True
        return super().remove_node(node)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def reset_dirty(self) -> None:
        self._dirty = False

    def set_dirty(self) -> None:
        self._dirty = True

    @property
    def cfg(self) -> Graph:
        def filter_node(node: Node) -> bool:
            return isinstance(node, ControlNode)

        def filter_edge(source: Node, target: Node, edge_key: int) -> bool:
            edge = self[source][target][edge_key]["type"]
            return isinstance(edge, ControlFlowEdge) and not (
                isinstance(edge, Order) and edge.back
            )

        return subgraph_view(self, filter_node, filter_edge)

    def construct_cfg_closure(self) -> None:
        """Construct transitive closure of control-flow graph portion of the PDG."""
        closure = transitive_closure(self.cfg, reflexive=None)
        for edge in closure.edges():
            if edge not in self.cfg.edges():
                source, trans_target = edge
                self.add_edge(source, trans_target, ORDER_TRANS)


__all__ = [
    "Graph",
    "Node",
    "ControlNode",
    "DataNode",
    "Loop",
    "LOOP",
    "Task",
    "Variable",
    "Expression",
    "IntermediateValue",
    "Literal",
    "CompositeLiteral",
    "ScalarLiteral",
    "Edge",
    "DEF",
    "USE",
    "ORDER",
    "ORDER_TRANS",
    "ORDER_BACK",
    "When",
    "WHEN",
    "Keyword",
    "Composition",
    "NodeLocation",
    "Input",
]
