from __future__ import annotations

from typing import TypeVar

from collections.abc import Callable

from networkx._types import EdgeAttrT, GraphAttrT, NodeT
from networkx.classes.multidigraph import MultiDiGraph

G = TypeVar("G", bound="MultiDiGraph[NodeT, GraphAttrT, EdgeAttrT]")  # type: ignore[valid-type]

def subgraph_view(
    G: G,
    filter_node: Callable[[NodeT], bool] = ...,
    filter_edge: Callable[[NodeT, NodeT, int], bool] = ...,
) -> G: ...
