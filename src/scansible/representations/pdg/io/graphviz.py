"""GraphViz exporting."""

from __future__ import annotations

import graphviz as gv

from .. import representation as rep


def get_node_shape(n: rep.Node) -> str:
    if isinstance(n, rep.Expression):
        return "box"

    if isinstance(n, (rep.Literal, rep.IntermediateValue, rep.Variable)):
        return "ellipse"

    return "diamond"


def get_node_label(n: rep.Node) -> str:
    if isinstance(n, rep.Expression):
        return n.expr

    if isinstance(n, rep.ScalarLiteral):
        return f"{n.type}:{n.value}"

    if isinstance(n, rep.Literal):
        return f"{n.type}"

    if isinstance(n, rep.IntermediateValue):
        return f"${n.identifier}"

    if isinstance(n, rep.Variable):
        return f"{n.name}@{n.version},{n.value_version}"

    if isinstance(n, rep.Task):
        return n.action

    return n.__class__.__name__


def dump_node(n: rep.Node, dot: gv.Digraph) -> None:
    node_id = str(n.node_id)
    shape = get_node_shape(n)
    label = get_node_label(n)

    dot.node(str(node_id), label=label, shape=shape)


def dump_edge(e: rep.Edge, source: rep.Node, target: rep.Node, dot: gv.Digraph) -> None:
    if isinstance(e, rep.Order) and e.transitive:
        return

    source_id = str(source.node_id)
    target_id = str(target.node_id)
    edge_label = e.__class__.__name__.upper()
    if isinstance(e, rep.Keyword):
        edge_label = e.keyword

    dot.edge(source_id, target_id, label=edge_label)


def dump_graph(g: rep.Graph) -> gv.Digraph:
    dot = gv.Digraph()

    for n in g:
        dump_node(n, dot)
    for src, target, e in g.edges(data=True):
        dump_edge(e["type"], src, target, dot)

    return dot
