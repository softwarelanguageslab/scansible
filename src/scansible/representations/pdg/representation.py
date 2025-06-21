"""Program Dependence Graph representation."""

from __future__ import annotations

from typing import Annotated, final, overload, override
from typing import Literal as LiteralT

import abc
import operator
from collections.abc import Callable, Iterable, Sequence
from functools import partial

import rustworkx as rx
from pydantic import BaseModel, Field, StringConstraints, field_validator

from scansible.types import ScalarValue

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


class ControlNode(Node): ...


class DataNode(Node): ...


class Task(ControlNode):
    """Node representing a task."""

    action: Annotated[str, StringConstraints(min_length=1)] = Field(frozen=True)
    name: str | None = Field(frozen=True, default=None)


class Variable(DataNode):
    """Node representing variables."""

    name: Annotated[str, StringConstraints(min_length=1)] = Field(frozen=True)
    version: int = Field(frozen=True)
    value_version: int = Field(frozen=True)
    scope_level: int = Field(frozen=True)


class IntermediateValue(DataNode):
    """Node representing intermediate values."""

    identifier: int = Field(frozen=True)


class Literal(DataNode):
    """Node representing a literal."""

    type: ValidTypeStr = Field(frozen=True)


class ScalarLiteral(Literal):
    value: ScalarValue = Field(frozen=True)


class CompositeLiteral(Literal):
    """Node representing a literal of a composite type."""


class Expression(DataNode):
    """Node representing a template expression."""

    expr: Annotated[str, StringConstraints(min_length=1)] = Field(frozen=True)
    is_conditional: bool = Field(frozen=True, default=False)
    orig_expr: str = Field(frozen=True, default="")

    impure_components: Sequence[str] = Field(frozen=True, default_factory=tuple)

    @property
    def is_pure(self) -> bool:
        return not self.impure_components

    @field_validator("impure_components", mode="after")
    @classmethod
    def _convert_impure_components_list(cls, value: Sequence[str]) -> tuple[str, ...]:
        # Needs to be a tuple for hashing, but when deserialising it could be
        # provided as a list (e.g., in the GraphML deserialiser or from JSON).
        return tuple(value)


class Edge(abc.ABC, _FrozenRepresentation, frozen=True):
    """Base edge."""

    @classmethod
    @abc.abstractmethod
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        raise NotImplementedError()


class ControlFlowEdge(Edge, frozen=True):
    """Edges representing control flow."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not (isinstance(source, ControlNode) and isinstance(target, ControlNode)):
            raise TypeError("Control flow edges are only allowed between control nodes")


class DataFlowEdge(Edge, abc.ABC, frozen=True):
    """Edges representing data flow."""


class Order(ControlFlowEdge, frozen=True):
    """Edges representing order between control nodes."""

    transitive: bool = False
    back: bool = False


class Notifies(ControlFlowEdge, frozen=True):
    """Edges representing notification from task to handler."""


class When(ControlFlowEdge, frozen=True):
    """Edges representing conditional execution from data node to task."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        # Can end in both data nodes (conditional definition) or control nodes (conditional execution)
        if not isinstance(source, DataNode):
            raise TypeError("Conditional edges are only allowed from data node")


class Loop(ControlFlowEdge, frozen=True):
    """Edges representing looping execution from data node (over which we iterate)
    to task."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not (isinstance(source, DataNode) and isinstance(target, ControlNode)):
            raise TypeError(
                "Loop edges are only allowed from data node to control nodes"
            )


class Use(DataFlowEdge, frozen=True):
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


class Input(Use, frozen=True):
    param_idx: int

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, DataNode):
            raise TypeError("Input edge must start at a data node")

        if not isinstance(target, Expression):
            raise TypeError("Input edges must only be used with expressions as target")


class Keyword(Use, frozen=True):
    """Edges representing data usage as a task keyword."""

    keyword: str

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(source, DataNode):
            raise TypeError("Keyword edge must start at a data node")

        if not isinstance(target, Task):
            raise TypeError("Keyword edges must only be used with tasks as target")


class Composition(Use, frozen=True):
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


class Def(DataFlowEdge, frozen=True):
    """Edges representing data definitions."""

    @classmethod
    @override
    def raise_if_disallowed(cls, source: Node, target: Node) -> None:
        if not isinstance(target, DataNode):
            raise TypeError("Def edges can only define data")
        if isinstance(target, Literal):
            raise TypeError("Def edges cannot define literals")


class DefLoopItem(Def, frozen=True):
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


def _edge_matcher(
    edge: Edge | None, edge_type: type[Edge] | None
) -> Callable[[Edge], bool]:
    if edge is not None and edge_type is not None:
        raise TypeError("edge and edge_type are mutually exclusive")

    if edge is not None:
        return partial(operator.eq, edge)
    elif edge_type is not None:
        return lambda e: isinstance(e, edge_type)
    else:
        raise TypeError("one of edge and edge_type must be provided")


@overload
def _filter_nodes[T: Node](nodes: list[Node], node_type: type[T]) -> Sequence[T]: ...
@overload
def _filter_nodes(
    nodes: list[Node], node_type: type[Node] | None
) -> Sequence[Node]: ...
def _filter_nodes(nodes: list[Node], node_type: type[Node] | None) -> Sequence[Node]:
    if node_type is None:
        return nodes
    return [node for node in nodes if isinstance(node, node_type)]


@final
class Graph:
    def __init__(self, role_name: str = "", role_version: str = "") -> None:
        # Composition over inheritance because we override some methods of the
        # existing class in incompatible ways. For instance, we don't want to
        # return node IDs in `add_node` and prefer to store them in the nodes
        # themselves, allowing `add_edge` to just take the nodes rather than
        # having the PDG builder need to keep track of node IDs separately.
        self._graph = rx.PyDiGraph[Node, Edge]()

        # FIXME: Names make no sense as PDGs are also built for playbooks. Moreover,
        # it's probably not strictly necessary to store this information in the
        # graph.
        self.role_name = role_name
        self.role_version = role_version
        self._dirty = False

    def add_node(self, node: Node) -> None:
        if node.node_id >= 0:
            # Node already added to graph, ignore
            assert self.has_node(node), "Node ID instantiated but not added?!"
            return

        node.node_id = self._graph.add_node(node)
        self._dirty = True

    def add_nodes(self, nodes: Iterable[Node]) -> None:
        # Adding one-by-one to reuse the checks above
        for node in nodes:
            self.add_node(node)

    def add_edge(self, n1: Node, n2: Node, edge: Edge) -> None:
        edge.raise_if_disallowed(n1, n2)

        # Prevent duplicate edges.
        # FIXME: Warn and fix builder to not add duplicate edges instead.
        if self.has_edge(n1, n2, edge):
            return

        self._dirty = True
        _ = self._graph.add_edge(n1.node_id, n2.node_id, edge)

    def has_node(self, node: Node) -> bool:
        return node.node_id >= 0 and self._graph.has_node(node.node_id)

    def has_edge(self, n1: Node, n2: Node, edge: Edge) -> bool:
        if not self._graph.has_edge(n1.node_id, n2.node_id):
            return False

        existing_edges = self.get_edges_between(n1, n2)
        return edge in existing_edges

    def has_successor(
        self,
        node: Node,
        *,
        edge: Edge | None = None,
        edge_type: type[Edge] | None = None,
    ) -> bool:
        """Check whether the given node has a successor through the given edge label.

        If `edge_type` is provided, only considers edges of the given type.
        If `edge` is provided, only considers edges that equal the given edge.
        If neither is provided, considers all edges."""
        if edge is None and edge_type is None:
            return bool(self._graph.successor_indices(node.node_id))
        try:
            _ = self._graph.find_adjacent_node_by_edge(
                node.node_id, _edge_matcher(edge, edge_type)
            )
            return True
        except rx.NoSuitableNeighbors:
            return False

    def has_predecessor(
        self,
        node: Node,
        *,
        edge: Edge | None = None,
        edge_type: type[Edge] | None = None,
    ) -> bool:
        """Check whether the given node has a predecessor through the given edge label.

        If `edge_type` is provided, only considers edges of the given type.
        If `edge` is provided, only considers edges that equal the given edge.
        If neither is provided, considers all edges."""
        if edge is None and edge_type is None:
            return bool(self._graph.predecessor_indices(node.node_id))
        try:
            _ = self._graph.find_predecessor_node_by_edge(
                node.node_id, _edge_matcher(edge, edge_type)
            )
            return True
        except rx.NoSuitableNeighbors:
            return False

    @overload
    def get_successors[T: Node](
        self, node: Node, *, node_type: type[T], edge_type: type[Edge]
    ) -> Sequence[T]: ...
    @overload
    def get_successors[T: Node](
        self, node: Node, *, node_type: type[T], edge: Edge
    ) -> Sequence[T]: ...
    @overload
    def get_successors[T: Node](
        self, node: Node, *, node_type: type[T]
    ) -> Sequence[T]: ...
    @overload
    def get_successors(
        self, node: Node, *, edge_type: type[Edge]
    ) -> Sequence[Node]: ...
    @overload
    def get_successors(self, node: Node, *, edge: Edge) -> Sequence[Node]: ...
    @overload
    def get_successors(self, node: Node) -> Sequence[Node]: ...
    def get_successors(
        self,
        node: Node,
        *,
        node_type: type[Node] | None = None,
        edge_type: type[Edge] | None = None,
        edge: Edge | None = None,
    ) -> Sequence[Node]:
        """Get successor nodes of the given node.

        If `node_type` is provided, this will only return nodes of that type.
        If `edge` is provided, this will only return successors through the given edge.
        Similarly, if `edge_type` is provided, this will only return successors through
        edges of the given type.
        `edge` and `edge_type` are mutually exclusive.
        """
        if edge is None and edge_type is None:
            nodes = self._graph.successors(node.node_id)
        else:
            nodes = self._graph.find_successors_by_edge(
                node.node_id, _edge_matcher(edge, edge_type)
            )

        return _filter_nodes(nodes, node_type)

    @overload
    def get_predecessors[T: Node](
        self, node: Node, *, node_type: type[T], edge_type: type[Edge]
    ) -> Sequence[T]: ...
    @overload
    def get_predecessors[T: Node](
        self, node: Node, *, node_type: type[T], edge: Edge
    ) -> Sequence[T]: ...
    @overload
    def get_predecessors[T: Node](
        self, node: Node, *, node_type: type[T]
    ) -> Sequence[T]: ...
    @overload
    def get_predecessors(
        self, node: Node, *, edge_type: type[Edge]
    ) -> Sequence[Node]: ...
    @overload
    def get_predecessors(self, node: Node, *, edge: Edge) -> Sequence[Node]: ...
    @overload
    def get_predecessors(self, node: Node) -> Sequence[Node]: ...
    def get_predecessors(
        self,
        node: Node,
        *,
        node_type: type[Node] | None = None,
        edge_type: type[Edge] | None = None,
        edge: Edge | None = None,
    ) -> Sequence[Node]:
        """Get predecessor nodes of the given node.

        If `node_type` is provided, this will only return nodes of that type.
        If `edge` is provided, this will only return predecessors through the given edge.
        Similarly, if `edge_type` is provided, this will only return predecessors through
        edges of the given type.
        `edge` and `edge_type` are mutually exclusive.
        """
        if edge is None and edge_type is None:
            nodes = self._graph.predecessors(node.node_id)
        else:
            nodes = self._graph.find_predecessors_by_edge(
                node.node_id, _edge_matcher(edge, edge_type)
            )

        return _filter_nodes(nodes, node_type)

    @overload
    def get_neighbors[T: Node](
        self, node: Node, *, node_type: type[T], edge_type: type[Edge]
    ) -> Sequence[T]: ...
    @overload
    def get_neighbors[T: Node](
        self, node: Node, *, node_type: type[T], edge: Edge
    ) -> Sequence[T]: ...
    @overload
    def get_neighbors[T: Node](
        self, node: Node, *, node_type: type[T]
    ) -> Sequence[T]: ...
    @overload
    def get_neighbors(self, node: Node, *, edge_type: type[Edge]) -> Sequence[Node]: ...
    @overload
    def get_neighbors(self, node: Node, *, edge: Edge) -> Sequence[Node]: ...
    @overload
    def get_neighbors(self, node: Node) -> Sequence[Node]: ...
    def get_neighbors(
        self,
        node: Node,
        *,
        node_type: type[Node] | None = None,
        edge_type: type[Edge] | None = None,
        edge: Edge | None = None,
    ) -> Sequence[Node]:
        """Get neighbors (successor or predecessor) nodes of the given node.

        If `node_type` is provided, this will only return nodes of that type.
        If `edge` is provided, this will only return neighbors through the given edge.
        Similarly, if `edge_type` is provided, this will only return neighbors through
        edges of the given type.
        `edge` and `edge_type` are mutually exclusive.
        """

        # Cannot delegate to get_successors or get_predecessors as this conflicts
        # with the static types: There is no overload that allows us to pass None
        # values to `node_type`, `edge_type`, or `edge`, nor one that allows us
        # to specify both `edge_type` and `edge`. We'd like to keep it that way
        # to minimise possibilities for client errors.

        if edge is None and edge_type is None:
            # PyDiGraph.neighbors returns node IDs instead of nodes.
            successors = self._graph.successors(node.node_id)
            predecessors = self._graph.predecessors(node.node_id)
        else:
            successors = self._graph.find_successors_by_edge(
                node.node_id, _edge_matcher(edge, edge_type)
            )
            predecessors = self._graph.find_predecessors_by_edge(
                node.node_id, _edge_matcher(edge, edge_type)
            )

        nodes = list(set(successors) | set(predecessors))

        return _filter_nodes(nodes, node_type)

    @overload
    def get_in_edges[T: Edge](
        self, node: Node, *, edge_type: type[T]
    ) -> Sequence[tuple[T, Node]]: ...
    @overload
    def get_in_edges(self, node: Node) -> Sequence[tuple[Edge, Node]]: ...
    def get_in_edges(
        self, node: Node, *, edge_type: type[Edge] | None = None
    ) -> Sequence[tuple[Edge, Node]]:
        """Get incoming edges of the given node.

        If `edge_type` is provided, this will only return edges of the given type.
        Not that contrary to node traversal operations, this method does not take
        an `edge` parameter, as its result will simply be either an empty list if
        the edge does not exist, or a list containing the edge if it does not.
        Instead, use `has_predecessor` with the `edge` parameter.
        """
        edges = self._graph.in_edges(node.node_id)

        if edge_type is None:
            edges_and_nodes = [(edge, pred) for pred, _, edge in edges]
        else:
            edges_and_nodes = [
                (edge, pred) for pred, _, edge in edges if isinstance(edge, edge_type)
            ]

        return [
            (edge, self._graph.get_node_data(pred)) for edge, pred in edges_and_nodes
        ]

    @overload
    def get_out_edges[T: Edge](
        self, node: Node, *, edge_type: type[T]
    ) -> Sequence[tuple[T, Node]]: ...
    @overload
    def get_out_edges(self, node: Node) -> Sequence[tuple[Edge, Node]]: ...
    def get_out_edges(
        self, node: Node, *, edge_type: type[Edge] | None = None
    ) -> Sequence[tuple[Edge, Node]]:
        """Get outgoing edges of the given node.

        If `edge_type` is provided, this will only return edges of the given type.
        Not that contrary to node traversal operations, this method does not take
        an `edge` parameter, as its result will simply be either an empty list if
        the edge does not exist, or a list containing the edge if it does not.
        Instead, use `has_successor` with the `edge` parameter.
        """
        edges = self._graph.out_edges(node.node_id)

        if edge_type is None:
            edges_and_nodes = [(edge, succ) for succ, _, edge in edges]
        else:
            edges_and_nodes = [
                (edge, succ) for succ, _, edge in edges if isinstance(edge, edge_type)
            ]

        return [
            (edge, self._graph.get_node_data(succ)) for edge, succ in edges_and_nodes
        ]

    @overload
    def get_edges_between[T: Edge](
        self, n1: Node, n2: Node, *, edge_type: type[T]
    ) -> Sequence[T]: ...
    @overload
    def get_edges_between(self, n1: Node, n2: Node) -> Sequence[Edge]: ...
    def get_edges_between(
        self, n1: Node, n2: Node, *, edge_type: type[Edge] | None = None
    ) -> Sequence[Edge]:
        """Get edges from n1 to n2.

        If `edge_type` is provided, this will only return edges of the given type.
        Not that contrary to node traversal operations, this method does not take
        an `edge` parameter, as its result will simply be either an empty list if
        the edge does not exist, or a list containing the edge if it does not.
        Instead, use `has_edge`.
        """
        try:
            edges = self._graph.get_all_edge_data(n1.node_id, n2.node_id)
            if edge_type is not None:
                edges = [edge for edge in edges if isinstance(edge, edge_type)]
            return edges
        except rx.NoEdgeBetweenNodes:
            return []

    @property
    def num_nodes(self) -> int:
        return self._graph.num_nodes()

    @property
    def nodes(self) -> list[Node]:
        return self._graph.nodes()

    def get_nodes[T: Node](self, node_type: type[T]) -> Sequence[T]:
        return _filter_nodes(self.nodes, node_type)

    @property
    def edges(self) -> list[tuple[Node, Node, Edge]]:
        return [
            (self._graph.get_node_data(n1), self._graph.get_node_data(n2), edge)
            for n1, n2, edge in self._graph.edge_index_map().values()
        ]

    @property
    def num_edges(self) -> int:
        return self._graph.num_edges()

    def _get_edge_id(self, n1: Node, n2: Node, edge: Edge) -> int | None:
        edge_indices = self._graph.edge_indices_from_endpoints(n1.node_id, n2.node_id)
        for edge_index in edge_indices:
            if self._graph.get_edge_data_by_index(edge_index) == edge:
                return edge_index

        return None

    def remove_edge(self, n1: Node, n2: Node, edge: Edge) -> None:
        edge_id = self._get_edge_id(n1, n2, edge)
        if edge_id is not None:
            self._dirty = True
            self._graph.remove_edge_from_index(edge_id)

    def remove_node(self, node: Node) -> None:
        self._dirty = True
        self._graph.remove_node(node.node_id)

    def replace_edge(self, n1: Node, n2: Node, old_edge: Edge, new_edge: Edge) -> None:
        new_edge.raise_if_disallowed(n1, n2)
        edge_index = self._get_edge_id(n1, n2, old_edge)
        assert edge_index is not None, "Cannot replace edge that does not exist"
        self._graph.update_edge_by_index(edge_index, new_edge)

    def replace_node(self, old_node: Node, new_node: Node) -> None:
        """Replace a node with another node, updating all edges to connect to the new node."""
        if new_node.node_id >= 0:
            raise ValueError("new node already exists in graph")

        new_node.node_id = self._graph.contract_nodes([old_node.node_id], new_node)

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def reset_dirty(self) -> None:
        self._dirty = False

    def set_dirty(self) -> None:
        self._dirty = True


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
