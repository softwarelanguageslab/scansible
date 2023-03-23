from __future__ import annotations

from typing import Any, Literal, Mapping, Sequence, overload

from networkx._types import EdgeAttrT, GraphAttrT, NodeT

from .digraph import DiGraph
from .multigraph import MultiGraph

class MultiDiGraph(
    MultiGraph[NodeT, GraphAttrT, EdgeAttrT], DiGraph[NodeT, GraphAttrT, EdgeAttrT]
):
    def __init__(
        self,
        incoming_graph_data: Any | None = ...,
        multigraph_input: Any | None = ...,
        **attr: GraphAttrT,
    ) -> None: ...
    def __getitem__(
        self, u: NodeT
    ) -> Mapping[NodeT, Mapping[int, Mapping[str, EdgeAttrT]]]: ...
    def add_edge(
        self,
        u_for_edge: NodeT,
        v_for_edge: NodeT,
        key: int | None = ...,
        **attr: EdgeAttrT,
    ) -> int: ...
    @overload
    def edges(self) -> Sequence[tuple[NodeT, NodeT]]: ...
    @overload
    def edges(
        self, *, data: Literal[True]
    ) -> Sequence[tuple[NodeT, NodeT, Mapping[str, EdgeAttrT]]]: ...
    @overload
    def edges(
        self, *, data: Literal[True], keys: Literal[True]
    ) -> Sequence[tuple[NodeT, NodeT, int, Mapping[str, EdgeAttrT]]]: ...
    def in_edges(
        self, node: NodeT, data: str
    ) -> Sequence[tuple[NodeT, NodeT, EdgeAttrT]]: ...
