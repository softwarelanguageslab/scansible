"""GraphViz exporting."""

from __future__ import annotations

import graphviz as gv

from .. import representation as rep


def get_node_attributes(n: rep.Node) -> dict[str, str]:
    match n:
        case rep.ControlNode():
            return {
                "style": "filled",
                "shape": "ellipse",
                "fillcolor": "lightgrey",
                "fontsize": "30",
            }
        case rep.Literal():
            return {
                "style": "dotted, filled",
                "fillcolor": "lightgrey",
            }
        case rep.IntermediateValue():
            return {
                "shape": "circle",
                "fontsize": "8",
            }
        case rep.Expression():
            return {
                "style": "dashed",
            }
        case rep.Variable():
            return {
                "style": "dotted",
            }
        case _:
            return {}


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
        return f"<<B>{n.action}</B>>"

    return n.__class__.__name__


def dump_node(n: rep.Node, dot: gv.Digraph) -> None:
    node_id = str(n.node_id)
    default_attrs = {"shape": "box"}
    attrs = get_node_attributes(n)
    label = get_node_label(n)

    dot.node(str(node_id), label=label, **(default_attrs | attrs))


def dump_edge(e: rep.Edge, source: rep.Node, target: rep.Node, dot: gv.Digraph) -> None:
    if isinstance(e, rep.Order) and e.transitive:
        return

    source_id = str(source.node_id)
    target_id = str(target.node_id)
    edge_label = e.__class__.__name__.upper()
    if isinstance(e, rep.Keyword):
        edge_label = e.keyword
    elif isinstance(e, rep.Composition):
        edge_label = e.index
    elif isinstance(e, rep.Input):
        edge_label = f"_{e.param_idx}"
    elif isinstance(e, rep.DefLoopItem) and e.loop_with is not None:
        edge_label = f"DEFLOOPITEM: {e.loop_with}"

    if isinstance(e, rep.Order) and e.transitive:
        dot.edge(
            source_id,
            target_id,
            label=edge_label,
            penwidth="2.5",
            style="dotted",
            color="grey",
        )
    elif isinstance(e, rep.Order):
        dot.edge(source_id, target_id, label=edge_label, weight="100", penwidth="2.5")
    else:
        dot.edge(source_id, target_id, label=edge_label)


def dump_graph(g: rep.Graph) -> gv.Digraph:
    dot = gv.Digraph()
    dot.attr("node", fontname="Courier")

    for n in g.nodes:
        dump_node(n, dot)
    for src, target, edge in g.edges:
        dump_edge(edge, src, target, dot)

    return dot
