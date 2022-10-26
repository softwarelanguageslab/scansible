"""Base role graphs."""

from collections.abc import Iterable

from networkx import MultiDiGraph

from .edges import Edge
from .nodes import Node

class Graph(MultiDiGraph):

    def __init__(self, role_name: str, role_version: str) -> None:
        super().__init__(role_name=role_name, role_version=role_version)
        self.errors: list[str] = []

    @property
    def role_name(self) -> str:
        return self.graph['role_name']

    @property
    def role_version(self) -> str:
        return self.graph['role_version']

    def add_node(self, node: Node) -> None:
        if not isinstance(node, Node):
            raise TypeError('Can only add Nodes to the graph')

        super().add_node(node)

    def add_nodes_from(self, nodes: Iterable[Node]) -> None:
        # Adding one-by-one to reuse the checks above
        for node in nodes:
            self.add_node(node)

    def add_edge(self, n1: Node, n2: Node, type: Edge) -> None:
        type.raise_if_disallowed(n1, n2)

        existing_edges = self.get_edge_data(n1, n2)
        for edge_data in (existing_edges or {}).values():
            if edge_data['type'] == type:
                return

        super().add_edge(n1, n2, type=type)
