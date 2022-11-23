"""Graph matcher assertion helpers."""
from typing import Any, Iterable

import operator

import attrs

from scansible.representations.pdg import Edge, Graph, Node, IntermediateValue


def _get_in_out_neighbours(g: Graph, n: Node) -> set[Node]:
    return set(g.predecessors(n)) | set(g.successors(n))


def _match_node(n1: Node, n2: Node) -> bool:
    def to_dict(n: Node) -> dict[str, Any]:
        return {k: v for k, v in attrs.asdict(n).items() if k not in ('node_id', 'location')}

    return (type(n1) == type(n2)
        and (not isinstance(n1, IntermediateValue) and to_dict(n1) == to_dict(n2)))


def get_graph_kws(g: Graph, ignore: set[str]) -> dict[str, Any]:
    return {k: v for k, v in g.graph.items() if k not in ignore}


def assert_graphs_match(g1: Graph, g2: Graph, ignore_graph_kws: set[str] | None = None) -> None:
    __tracebackhide__ = True

    if ignore_graph_kws is None:
        ignore_graph_kws = set()

    if get_graph_kws(g1, ignore_graph_kws) != get_graph_kws(g2, ignore_graph_kws):
        raise AssertionError(f'Mismatching graph attributes: Expected {g2.graph}, got {g1.graph}')

    # Compare nodes
    nodes1 = set(g1)
    nodes2 = set(g2)
    correspondences: dict[Node, Node] = {}
    for n1 in sorted(nodes1, key=operator.attrgetter('node_id')):
        if isinstance(n1, IntermediateValue):
            continue

        for n2 in sorted(nodes2, key=operator.attrgetter('node_id')):
            if _match_node(n1, n2):
                nodes2.remove(n2)
                correspondences[n1] = n2
                break
        else:
            raise AssertionError(f'Unexpected node {n1!r} in first graph')

    for n2 in nodes2:
        if not isinstance(n2, IntermediateValue):
            raise AssertionError(f'Missing node {n2!r} in first graph')

    # Construct correspondences between intermediate values
    for n1 in nodes1:
        if n1 in correspondences:
            continue
        assert isinstance(n1, IntermediateValue), 'Only IVs expected here'
        connected_nodes = _get_in_out_neighbours(g1, n1)

        if not connected_nodes:
            raise AssertionError('Disconnected intermediate value in first graph. Cannot handle that')

        if any(isinstance(cn, IntermediateValue) for cn in connected_nodes):
            raise AssertionError(f'Chain of intermediate values with {n1!r} in first graph. Cannot handle those.')

        conn_in_g2 = {correspondences[cn] for cn in connected_nodes}
        assert len(conn_in_g2) == len(connected_nodes)

        candidates = [cand for cn2 in conn_in_g2 for cand in _get_in_out_neighbours(g2, cn2)]
        found = False
        for cand in candidates:
            if not isinstance(cand, IntermediateValue):
                continue
            if _get_in_out_neighbours(g2, cand) == conn_in_g2 and cand in nodes2:
                if found:
                    raise AssertionError('Multiple intermediate values between same nodes. Cannot handle that.')
                found = True
                correspondences[n1] = cand
                nodes2.remove(cand)
                break
        else:
            raise AssertionError(f'Unexpected intermediate value {n1!r} of first graph (connected to {connected_nodes}')

    for n2 in nodes2:
        raise AssertionError(f'Missing intermediate value {n2!r} in first graph')

    # Compare edges
    edges1 = set(g1.edges())
    edges2 = set(g2.edges())
    for e1 in edges1:
        e2 = (correspondences[e1[0]], correspondences[e1[1]])

        if e2 not in edges2:
            raise AssertionError(f'Unexpected edge {e1[0]!r} -> {e1[1]!r} in first graph')

        edges2.remove(e2)

        d1 = g1[e1[0]][e1[1]]
        d2 = g2[e2[0]][e2[1]]
        if d1 != d2:
            raise AssertionError(f'Mismatch in edge data for {e2[0]!r} -> {e2[1]!r}: Expected {d2}, got {d1}')

    for e2 in edges2:
        raise AssertionError(f'Missing edge {e2[0]!r} -> {e2[1]!r} in first graph')


NodeSpecs = dict[str, Node]
EdgeSpecs = Iterable[tuple[str, str, Edge]]

def create_graph(nodes: NodeSpecs, edges: EdgeSpecs, role_name: str = 'test_role', role_version: str = 'test_version') -> Graph:
    g = Graph(role_name=role_name, role_version=role_version)
    g.add_nodes_from(nodes.values())
    for src, target, edge in edges:
        g.add_edge(nodes[src], nodes[target], edge)
    return g
