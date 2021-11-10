"""Neo4j exporting."""
from typing import Any

import json

from pydantic import BaseModel

from ..models.edges import Edge, Order
from ..models.graph import Graph
from ..models.nodes import Node


def _get_shared_node_attrs(g: Graph) -> dict[str, str]:
    return {'role_name': g.role_name, 'role_version': g.role_version}


def dump_value(v: Any) -> str:
    if isinstance(v, str):
        return json.dumps(v)
    if v is None:
        return 'null'
    return str(v)

def _create_attr_content(attrs: dict[str, Any]) -> str:
    return ', '.join(
            f'{attr_key}: {dump_value(attr_value)}'
            for attr_key, attr_value in sorted(attrs.items()))

def dump_node(n: Node, g: Graph) -> str:
    node_label = n.__class__.__name__
    node_id = n.node_id
    node_attrs = dict(n) | _get_shared_node_attrs(g)

    attr_content = _create_attr_content(node_attrs)

    return f'CREATE (n{node_id}:{node_label} {{ {attr_content} }})'


def dump_edge(e: Edge, source: Node, target: Node) -> str:
    source_id = source.node_id
    target_id = target.node_id
    edge_label = e.__class__.__name__.upper()

    if isinstance(e, Order) and e.transitive:
        return ''

    if isinstance(e, BaseModel):
        attr_content = _create_attr_content(dict(e))
        edge_spec = f':{edge_label} {{ {attr_content} }}'
    else:
        edge_spec = f':{edge_label}'

    return f'CREATE (n{source_id})-[{edge_spec}]->(n{target_id})'


def dump_graph(g: Graph) -> str:
    node_strs = [dump_node(n, g) for n in g.nodes]
    edge_strs = [
            dump_edge(e['type'], src, target)
            for (src, target, e) in g.edges(data=True)]

    query = '\n'.join([s for s in node_strs + edge_strs if s])
    if not query:
        return ''

    return query + ';'
