"""Graph matcher assertion helpers."""

from __future__ import annotations

import operator
from collections.abc import Iterable

from scansible.representations.pdg import Edge, Graph, IntermediateValue, Node


def _match_node(n1: Node, n2: Node, match_locations: bool) -> bool:
    ignored_kws = {"node_id"} if match_locations else {"node_id", "location"}

    return type(n1) is type(n2) and (
        not isinstance(n1, IntermediateValue)
        and n1.model_dump(exclude=ignored_kws) == n2.model_dump(exclude=ignored_kws)
    )


def assert_graphs_match(
    g1: Graph,
    g2: Graph,
    *,
    match_locations: bool = False,
) -> None:
    __tracebackhide__ = True

    assert g1.role_name == g2.role_name, (
        f"Mismatching role name: Expected {g2.role_name}, got {g1.role_name}"
    )
    assert g1.role_version == g2.role_version, (
        f"Mismatching role version: Expected {g2.role_version}, got {g1.role_version}"
    )

    # Compare nodes
    nodes1 = set(g1.nodes)
    nodes2 = set(g2.nodes)
    correspondences: dict[Node, Node] = {}
    for n1 in sorted(nodes1, key=operator.attrgetter("node_id")):
        if isinstance(n1, IntermediateValue):
            continue

        for n2 in sorted(nodes2, key=operator.attrgetter("node_id")):
            if _match_node(n1, n2, match_locations):
                nodes2.remove(n2)
                correspondences[n1] = n2
                break
        else:
            raise AssertionError(f"Unexpected node {n1!r} in first graph")

    for n2 in nodes2:
        if not isinstance(n2, IntermediateValue):
            raise AssertionError(f"Missing node {n2!r} in first graph")

    # Construct correspondences between intermediate values.
    # For every n1 in g1, find a node n2 in g2 whose neighbours all correspond
    # to n1's neighbors.
    for n1 in nodes1:
        if n1 in correspondences:
            continue
        assert isinstance(n1, IntermediateValue), "Only IVs expected here"
        n1_neighbors = g1.get_neighbors(n1)

        if not n1_neighbors:
            raise AssertionError(
                "Disconnected intermediate value in first graph. Cannot handle that"
            )

        if any(isinstance(cn, IntermediateValue) for cn in n1_neighbors):
            raise AssertionError(
                f"Chain of intermediate values with {n1!r} in first graph. Cannot handle those."
            )

        # Map n1's neighbors to the corresponding nodes in g2.
        n1_neighbors_in_g2 = {correspondences[cn] for cn in n1_neighbors}
        assert len(n1_neighbors_in_g2) == len(n1_neighbors)

        # All candidate n2s, which are all neighbors of the n1's neighbors mapped in g2.
        n2_candidates = [
            cand for cn2 in n1_neighbors_in_g2 for cand in g2.get_neighbors(cn2)
        ]
        found = False
        for cand in n2_candidates:
            if not isinstance(cand, IntermediateValue):
                continue
            if set(g2.get_neighbors(cand)) == n1_neighbors_in_g2 and cand in nodes2:
                if found:
                    raise AssertionError(
                        "Multiple intermediate values between same nodes. Cannot handle that."
                    )
                found = True
                correspondences[n1] = cand
                nodes2.remove(cand)
                break
        else:
            raise AssertionError(
                f"Unexpected intermediate value {n1!r} of first graph (connected to {n1_neighbors}"
            )

    for n2 in nodes2:
        raise AssertionError(f"Missing intermediate value {n2!r} in first graph")

    # Compare edges
    edges1 = set(g1.edges)
    edges2 = set(g2.edges)
    for e1_src, e1_target, e1_edge in edges1:
        e2 = (correspondences[e1_src], correspondences[e1_target], e1_edge)

        if e2 not in edges2:
            raise AssertionError(
                f"Unexpected edge {e1_src!r} -[{e1_edge}]-> {e1_target!r} in first graph"
            )

        edges2.remove(e2)

    for e2_src, e2_target, e2_edge in edges2:
        raise AssertionError(
            f"Missing edge {e2_src!r} -[{e2_edge}]-> {e2_target!r} in first graph"
        )


NodeSpecs = dict[str, Node]
EdgeSpecs = Iterable[tuple[str, str, Edge]]


def create_graph(
    nodes: NodeSpecs,
    edges: EdgeSpecs,
    role_name: str = "test_role",
    role_version: str = "test_version",
) -> Graph:
    g = Graph(role_name=role_name, role_version=role_version)
    g.add_nodes(nodes.values())
    for src, target, edge in edges:
        g.add_edge(nodes[src], nodes[target], edge)
    return g
