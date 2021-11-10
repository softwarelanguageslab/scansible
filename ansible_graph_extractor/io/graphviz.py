"""Neo4j exporting."""
from typing import Any

import json

from pydantic import BaseModel

from ..models.edges import Edge, Order
from ..models.graph import Graph
from ..models.nodes import Node, Task, Variable, Literal, Expression, IntermediateValue


def _get_shared_node_attrs(g: Graph) -> dict[str, str]:
    return {'role_name': g.role_name, 'role_version': g.role_version}


def dump_value(v: Any) -> str:
    if isinstance(v, str):
        return json.dumps(v)

    return str(v)

def _create_attr_content(attrs: dict[str, Any]) -> str:
    return ', '.join(
            f'{attr_key}: {dump_value(attr_value)}'
            for attr_key, attr_value in sorted(attrs.items()))


def get_node_shape(n: Node) -> str:
    if isinstance(n, Expression):
        return 'box'

    if isinstance(n, (Literal, IntermediateValue, Variable)):
        return 'ellipse'

    return 'diamond'


def get_node_label(n: Node) -> str:
    if isinstance(n, Expression):
        return n.expr

    if isinstance(n, Literal):
        return str(n.value)

    if isinstance(n, IntermediateValue):
        return f'${n.identifier}'

    if isinstance(n, Variable):
        return n.name

    if isinstance(n, Task):
        return n.action

    return ''

def dump_node(n: Node, g: Graph) -> str:
    node_id = n.node_id
    shape = get_node_shape(n)
    label = json.dumps(get_node_label(n))

    return f'{node_id} [shape={shape} label={label}];'


def dump_edge(e: Edge, source: Node, target: Node) -> str:
    source_id = source.node_id
    target_id = target.node_id
    edge_label = e.__class__.__name__.upper()

    if isinstance(e, Order) and e.transitive:
        return ''

    return f'{source_id} -> {target_id} [label="{edge_label}"];'


def dump_graph(g: Graph) -> str:
    node_strs = [dump_node(n, g) for n in g.nodes]
    edge_strs = [
            dump_edge(e['type'], src, target)
            for (src, target, e) in g.edges(data=True)]

    dot = 'digraph G {\n'
    dot += '\n'.join(node_strs + edge_strs)

    return dot + '\n}'
