"""Neo4j exporting."""

from __future__ import annotations

import json

from .. import representation as rep


def dump_value(v: object, attr_key: str) -> str:
    if isinstance(v, (tuple, list, dict)):
        # Need to wrap [] and {} into quotes.
        return dump_value(json.dumps(v), attr_key)
    return json.dumps(v)


def _create_attr_content(attrs: dict[str, object]) -> str:
    return ", ".join(
        f"{attr_key}: {dump_value(attr_value, attr_key)}"
        for attr_key, attr_value in sorted(attrs.items())
    )


def dump_node(n: rep.Node) -> str:
    node_label = n.__class__.__name__
    node_id = n.node_id
    node_attrs = n.model_dump()
    # A synthetic (i.e. unknown) location carries no useful information, so
    # export it as absent rather than as a placeholder location value.
    if n.location.is_synthetic:
        node_attrs["location"] = None

    attr_content = _create_attr_content(node_attrs)

    return f"(n{node_id}:{node_label} {{ {attr_content} }})"


def dump_edge(e: rep.Edge, source: rep.Node, target: rep.Node) -> str:
    source_id = source.node_id
    target_id = target.node_id
    edge_label = e.__class__.__name__.upper()

    if isinstance(e, rep.Order) and e.transitive:
        return ""

    attr_content = _create_attr_content(e.model_dump())
    if attr_content:
        edge_spec = f":{edge_label} {{ {attr_content} }}"
    else:
        edge_spec = f":{edge_label}"

    return f"(n{source_id})-[{edge_spec}]->(n{target_id})"


def dump_graph(g: rep.Graph) -> str:
    node_strs = [dump_node(n) for n in g.nodes]
    edge_strs = [dump_edge(edge, src, target) for (src, target, edge) in g.edges]

    query = ", \n".join([s for s in node_strs + edge_strs if s])
    if not query:
        return ""

    return "CREATE " + query
