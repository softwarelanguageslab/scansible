"""GraphML importer/exporter."""
from __future__ import annotations

from typing import Any, Type, TYPE_CHECKING

import json
from xml.etree.ElementTree import Element

import attrs
from networkx import Graph
from networkx.readwrite.graphml import GraphMLReader, GraphMLWriter

from .. import representation as rep

if TYPE_CHECKING:
    from networkx.readwrite.graphml import GraphMLKeys
    WriterBase = GraphMLWriter[rep.Node, Any, rep.Edge]
    ReaderBase = GraphMLReader[rep.Graph]
else:
    WriterBase = GraphMLWriter
    ReaderBase = GraphMLReader

class CustomGraphMLWriter(WriterBase):

    def _add_edge_attributes(
            self, scope: str, xml_obj: Element, edge: rep.Edge,
            default: dict[str, object]
    ) -> None:
        self.attribute_types[('type', scope)].add(str)
        self.attributes[xml_obj].append(('type', edge.__class__.__name__.upper(), scope, default.get('type')))
        if attrs.has(type(edge)):
            for k, v in attrs.asdict(edge).items():
                self.attribute_types[(k, scope)].add(str)
                self.attributes[xml_obj].append((k, json.dumps(v), scope, default.get(k)))

    def add_nodes(self, g: Graph[rep.Node, Any, rep.Edge], graph_element: Element) -> None:
        for node, _ in g.nodes(data=True):
            node_element = self.myElement('node', id=str(node.node_id))
            self.add_attributes('node', node_element, self._dump_node_attributes(node), {})
            graph_element.append(node_element)

    def _dump_node_attributes(self, node: rep.Node) -> dict[str, str]:
        result = {
            'node_type': node.__class__.__name__,
        }
        for k, v in attrs.asdict(node).items():
            if v is None:
                continue
            result[k] = json.dumps(v)
        return result

    def add_edges(self, g: Graph[rep.Node, Any, rep.Edge], graph_element: Element) -> None:
        assert isinstance(g, rep.Graph)

        for u, v, key, data in g.edges(data=True, keys=True):
            edge_element = self.myElement(
                    'edge', source=str(u.node_id), target=str(v.node_id),
                    id=str(key))
            self._add_edge_attributes('edge', edge_element, data['type'], {})
            graph_element.append(edge_element)


class CustomGraphMLReader(ReaderBase):

    def __init__(self, node_type: Type[rep.Node] = rep.Node, edge_key_type: Type[int] = int, force_multigraph: bool = False) -> None:
        super().__init__(node_type, edge_key_type, force_multigraph)
        self._node_map: dict[int, rep.Node] = {}
        self.multigraph = True

    def make_graph(self, graph_xml: Element, graphml_keys: dict[str, GraphMLKeys], defaults: object, G: rep.Graph | None = None) -> rep.Graph:
        data = self.decode_data_elements(graphml_keys, graph_xml)
        return super().make_graph(graph_xml, graphml_keys, defaults, rep.Graph(**data))

    def add_node(self, g: rep.Graph, node_xml: Element, graphml_keys: dict[str, GraphMLKeys], defaults: object) -> None:
        # get data/attributes for node
        data = self.decode_data_elements(graphml_keys, node_xml)
        node = self._load_node(data)

        self._node_map[node.node_id] = node
        g.add_node(node)

    def _load_node(self, data: dict[str, str]) -> rep.Node:
        node_type = data['node_type']
        node_cls: Type[rep.Node] = getattr(rep, node_type)

        node_attrs = {k: json.loads(v) for k, v in data.items() if k not in ('node_type', 'node_id')}
        if 'location' in node_attrs:
            node_attrs['location'] = rep.NodeLocation(**node_attrs['location'])

        node = node_cls(**node_attrs)
        node.node_id = json.loads(data['node_id'])
        return node

    def add_edge(self, g: rep.Graph, edge_element: Element, graphml_keys: dict[str, GraphMLKeys]) -> None:
        source = self._node_map[int(edge_element.get('source'))]  # type: ignore[arg-type]
        target = self._node_map[int(edge_element.get('target'))]  # type: ignore[arg-type]
        data = self.decode_data_elements(graphml_keys, edge_element)

        edge_type = data['type']
        edge = getattr(rep, data['type'], None)
        if edge is None:
            edge_cls = getattr(rep, edge_type_to_name.get(data['type'], data['type'].title()))
            edge = edge_cls(**{k: json.loads(v) for k, v in data.items() if k != 'type'})

        g.add_edge(source, target, edge)


edge_type_to_name = {
    'DEFLOOPITEM': 'DefLoopItem',
    'DEFINEDIF': 'DefinedIf',
}

def dump_graph(g: rep.Graph) -> str:
    if not g:
        return ''

    writer = CustomGraphMLWriter(prettyprint=True)
    writer.add_graph_element(g)
    return str(writer)


def import_graph(graphml_str: str, role_id: str, role_version: str) -> rep.Graph:
    if not graphml_str:
        return rep.Graph(role_id, role_version)

    reader = CustomGraphMLReader()

    graphs = list(reader(string=graphml_str))
    assert len(graphs) == 1

    return graphs[0]
