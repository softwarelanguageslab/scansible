from __future__ import annotations

from typing import Mapping, TypeVar, overload

from networkx._types import EdgeAttrT, GraphAttrT, NodeT

from .graph import Graph

DefaultT = TypeVar("DefaultT")

class MultiGraph(Graph[NodeT, GraphAttrT, EdgeAttrT]):
    def has_edge(self, u: NodeT, v: NodeT, key: int | None = ...) -> bool: ...
    @overload
    def get_edge_data(
        self, u: NodeT, v: NodeT
    ) -> Mapping[int, Mapping[str, EdgeAttrT]] | None: ...
    @overload
    def get_edge_data(
        self, u: NodeT, v: NodeT, default: DefaultT
    ) -> Mapping[int, Mapping[str, EdgeAttrT]] | DefaultT: ...
    @overload
    def get_edge_data(
        self, u: NodeT, v: NodeT, key: int
    ) -> Mapping[str, EdgeAttrT] | None: ...
    @overload
    def get_edge_data(
        self, u: NodeT, v: NodeT, key: int, default: DefaultT
    ) -> Mapping[str, EdgeAttrT] | DefaultT: ...
