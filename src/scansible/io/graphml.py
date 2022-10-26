"""GraphML importer/exporter."""
from typing import Any

from networkx.readwrite.graphml import GraphMLReader, GraphMLWriter
from pydantic import BaseModel

from ..models import edges, nodes
from ..models.graph import Graph

class CustomGraphMLWriter(GraphMLWriter):

    def _add_edge_attributes(
            self, scope: str, xml_obj: object, edge: edges.Edge,
            default: dict[str, object]
    ) -> None:
        self.attribute_types[('type', scope)].add(str)
        self.attributes[xml_obj].append(['type', edge.__class__.__name__.upper(), scope, default.get('type')])
        if isinstance(edge, BaseModel):
            for k, v in dict(edge).items():
                self.attribute_types[(k, scope)].add(type(v))
                self.attributes[xml_obj].append([k, v, scope, default.get(k)])

    def add_nodes(self, g: Graph, graph_element: Any):
        default = g.graph.get('node_default', {})
        for node, _ in g.nodes(data=True):
            node_element = self.myElement('node', id=str(node.node_id))
            self.add_attributes('node', node_element, {k: v for k, v in dict(node).items() if v is not None}, default)
            self.add_attributes('node', node_element, {'node_type': node.__class__.__name__}, default)
            graph_element.append(node_element)

    def add_edges(self, g: Graph, graph_element: Any):
        assert g.is_multigraph()

        for u, v, key, data in g.edges(data=True, keys=True):
            edge_element = self.myElement(
                    'edge', source=str(u.node_id), target=str(v.node_id),
                    id=str(key))
            default = g.graph.get('edge_default', {})
            self._add_edge_attributes('edge', edge_element, data['type'], default)
            graph_element.append(edge_element)


class CustomGraphMLReader(GraphMLReader):

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._node_map: dict[int, nodes.Node] = {}
        self.multigraph = True

    def make_graph(self, graph_xml: Any, graphml_keys: Any, defaults: Any, g: Any = None) -> Graph:
        data = self.decode_data_elements(graphml_keys, graph_xml)
        return super().make_graph(graph_xml, graphml_keys, defaults, Graph(**data))

    def add_node(self, g: Graph, node_xml: Any, graphml_keys: Any, defaults: Any) -> None:
        # get data/attributes for node
        data = self.decode_data_elements(graphml_keys, node_xml)
        node_type = data['node_type']
        node_cls = getattr(nodes, node_type)

        node = node_cls(**{k: v for k, v in data.items() if k != 'node_type'})
        self._node_map[node.node_id] = node
        g.add_node(node)

    def add_edge(self, g: Graph, edge_element: Any, graphml_keys: Any) -> None:
        source = self._node_map[int(edge_element.get('source'))]
        target = self._node_map[int(edge_element.get('target'))]
        data = self.decode_data_elements(graphml_keys, edge_element)

        edge_type = data['type']
        edge = getattr(edges, data['type'], None)
        if edge is None:
            edge_cls = getattr(edges, edge_type_to_name.get(data['type'], data['type'].title()))
            edge = edge_cls(**{k: v for k, v in data.items() if k != 'type'})

        g.add_edge(source, target, edge)


edge_type_to_name = {
    'DEFLOOPITEM': 'DefLoopItem',
    'DEFINEDIF': 'DefinedIf',
}

def dump_graph(g: Graph) -> str:
    if not g:
        return ''

    writer = CustomGraphMLWriter(prettyprint=True)
    writer.add_graph_element(g)
    return str(writer)


def import_graph(graphml_str: str, role_id: str, role_version: str) -> Graph:
    if not graphml_str:
        return Graph(role_id, role_version)

    reader = CustomGraphMLReader()

    graphs = list(reader(string=graphml_str))
    assert len(graphs) == 1

    return graphs[0]
