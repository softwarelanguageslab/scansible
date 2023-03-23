from __future__ import annotations

from ..representation import Graph
from .graphml import dump_graph as graphml_dump
from .graphviz import dump_graph as dot_dump
from .neo4j import dump_graph as neo4j_dump


def dump_graph(output_format: str, graph: Graph) -> str:
    match output_format:
        case "graphml":
            dumper = graphml_dump
        case "neo4j":
            dumper = neo4j_dump
        case "graphviz":
            dumper = lambda g: dot_dump(g).source
        case _:
            raise ValueError(f"Unknown output format: {output_format}")

    return dumper(graph)
