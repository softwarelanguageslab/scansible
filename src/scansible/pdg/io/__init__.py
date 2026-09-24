from __future__ import annotations

from typing import TYPE_CHECKING

from .graphviz import dump_graph as dot_dump
from .neo4j import dump_graph as neo4j_dump

if TYPE_CHECKING:
    from collections.abc import Callable

    from ..representation import Graph


def graphviz_dump(graph: Graph) -> str:
    return dot_dump(graph).source


def dump_graph(output_format: str, graph: Graph) -> str:
    dumper: Callable[[Graph], str]
    match output_format:
        case "graphml":
            raise ValueError("GraphML output has been (temporarily?) removed.")
        case "neo4j":
            dumper = neo4j_dump
        case "graphviz":
            dumper = graphviz_dump
        case _:
            raise ValueError(f"Unknown output format: {output_format}")

    return dumper(graph)
