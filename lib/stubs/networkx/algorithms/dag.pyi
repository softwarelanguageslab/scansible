from __future__ import annotations

from typing import TypeVar

from networkx.classes.graph import Graph

G = TypeVar("G", bound=Graph)  # type: ignore[type-arg]

def transitive_closure(G: G, reflexive: bool | None = ...) -> G: ...
