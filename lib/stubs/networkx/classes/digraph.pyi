from __future__ import annotations

from typing import Iterator

from networkx._types import EdgeAttrT, GraphAttrT, NodeT

from .graph import Graph

class DiGraph(Graph[NodeT, GraphAttrT, EdgeAttrT]):
    def successors(self, n: NodeT) -> Iterator[NodeT]: ...
    def predecessors(self, n: NodeT) -> Iterator[NodeT]: ...
