"""Neo4j exporting."""
from typing import Any

import json

import attrs

from .. import Graph, Node, Edge, representation as rep


def _get_shared_node_attrs(g: Graph) -> dict[str, str]:
    return {'role_name': g.role_name, 'role_version': g.role_version}


def dump_value(v: Any) -> str:
    if isinstance(v, (tuple, list, dict)):
        # Need to wrap [] and {} into quotes.
        return dump_value(json.dumps(v))
    return json.dumps(v)

def _create_attr_content(attrs: dict[str, Any]) -> str:
    return ', '.join(
            f'{attr_key}: {dump_value(attr_value)}'
            for attr_key, attr_value in sorted(attrs.items()))

def dump_node(n: Node, g: Graph) -> str:
    node_label = n.__class__.__name__
    node_id = n.node_id
    node_attrs = attrs.asdict(n) | _get_shared_node_attrs(g)

    attr_content = _create_attr_content(node_attrs)

    return f'CREATE (n{node_id}:{node_label} {{ {attr_content} }})'


def dump_edge(e: Edge, source: Node, target: Node) -> str:
    source_id = source.node_id
    target_id = target.node_id
    edge_label = e.__class__.__name__.upper()

    if isinstance(e, rep.Order) and e.transitive:
        return ''

    if attrs.has(type(e)):
        attr_content = _create_attr_content(attrs.asdict(e))
        edge_spec = f':{edge_label} {{ {attr_content} }}'
    else:
        edge_spec = f':{edge_label}'

    return f'CREATE (n{source_id})-[{edge_spec}]->(n{target_id})'


def dump_graph(g: Graph) -> str:
    node_strs = [dump_node(n, g) for n in g]
    edge_strs = [
            dump_edge(e['type'], src, target)
            for (src, target, e) in g.edges(data=True)]

    query = '\n'.join([s for s in node_strs + edge_strs if s])
    if not query:
        return ''

    return query + ';'
