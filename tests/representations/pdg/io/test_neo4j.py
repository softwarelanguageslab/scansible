# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import Literal as LiteralT

import pytest

from scansible.representations.pdg import (
    DEF,
    ORDER,
    USE,
    Expression,
    Graph,
    Keyword,
    Literal,
    Node,
    NodeLocation,
    Task,
    Variable,
)
from scansible.representations.pdg.io.neo4j import dump_edge, dump_graph, dump_node


@pytest.fixture
def g() -> Graph:
    return Graph("testrole", "v1.0.0")


def describe_dump_node() -> None:
    def should_dump_expression(g: Graph) -> None:
        e = Expression(expr="{{ test }}")
        e.node_id = 0

        result = dump_node(e, g)

        assert (
            result
            == '(n0:Expression { expr: "{{ test }}", impure_components: "[]", location: null, node_id: 0, role_name: "testrole", role_version: "v1.0.0" })'
        )

    def should_dump_variable(g: Graph) -> None:
        v = Variable(name="test", version=0, value_version=0, scope_level=1)
        v.node_id = 0

        result = dump_node(v, g)

        assert (
            result
            == '(n0:Variable { location: null, name: "test", node_id: 0, role_name: "testrole", role_version: "v1.0.0", scope_level: 1, value_version: 0, version: 0 })'
        )

    def should_dump_task(g: Graph) -> None:
        t = Task(action="file", name="task name")
        t.node_id = 0

        result = dump_node(t, g)

        assert (
            result
            == '(n0:Task { action: "file", location: null, name: "task name", node_id: 0, role_name: "testrole", role_version: "v1.0.0" })'
        )

    def should_dump_task_with_location(g: Graph) -> None:
        t = Task(
            action="file", name="task name", location=NodeLocation("test.yml", 1, 10)
        )
        t.node_id = 0

        result = dump_node(t, g)

        assert (
            result
            == '(n0:Task { action: "file", location: "{\\"file\\": \\"test.yml\\", \\"line\\": 1, \\"column\\": 10, \\"includer_location\\": null}", name: "task name", node_id: 0, role_name: "testrole", role_version: "v1.0.0" })'
        )

    def should_dump_literal_string(g: Graph) -> None:
        l = Literal(type="str", value="literal value")
        l.node_id = 0

        result = dump_node(l, g)

        assert (
            result
            == '(n0:Literal { location: null, node_id: 0, role_name: "testrole", role_version: "v1.0.0", type: "str", value: "literal value" })'
        )

    @pytest.mark.parametrize(
        "type, value",
        [
            ("int", 0),
            ("int", 10),
            ("int", -10),
            ("float", 0.0),
            ("float", 0.10),
            ("float", -0.10),
            ("bool", True),
            ("bool", False),
        ],
    )
    def should_dump_literal_non_string(
        g: Graph, type: LiteralT["int", "float", "bool"], value: int | float | bool
    ) -> None:
        l = Literal(type=type, value=value)
        l.node_id = 0

        result = dump_node(l, g)

        assert (
            result
            == f'(n0:Literal {{ location: null, node_id: 0, role_name: "testrole", role_version: "v1.0.0", type: "{type}", value: {str(value).lower()} }})'
        )


def describe_dump_edge() -> None:
    def should_dump_order_edge() -> None:
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = ORDER

        result = dump_edge(e, n1, n2)

        assert result == "(n1)-[:ORDER { back: false, transitive: false }]->(n2)"

    def should_dump_def_edge() -> None:
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = DEF

        result = dump_edge(e, n1, n2)

        assert result == "(n1)-[:DEF]->(n2)"

    def should_dump_use_edge() -> None:
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = USE

        result = dump_edge(e, n1, n2)

        assert result == "(n1)-[:USE]->(n2)"

    def should_dump_keyword_edge() -> None:
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = Keyword(keyword="the.keyword")

        result = dump_edge(e, n1, n2)

        assert result == '(n1)-[:KEYWORD { keyword: "the.keyword" }]->(n2)'


def describe_dump_graph() -> None:
    def should_return_empty_query_for_empty_graph(g: Graph) -> None:
        result = dump_graph(g)

        assert not result

    def should_return_query_for_graph_with_single_node(g: Graph) -> None:
        t = Task(action="file", name="task name")
        t.node_id = 0
        g.add_node(t)

        result = dump_graph(g)

        assert result == "CREATE " + dump_node(t, g)

    def should_return_query_for_graph_with_multiple_nodes_without_edges(
        g: Graph,
    ) -> None:
        t = Task(action="file", name="task name")
        t.node_id = 0
        v = Variable(name="avar", version=0, value_version=0, scope_level=1)
        v.node_id = 1
        g.add_node(t)
        g.add_node(v)

        result = dump_graph(g)

        assert result == "CREATE " + ", \n".join([dump_node(t, g), dump_node(v, g)])

    def should_return_query_for_graph_with_multiple_nodes_with_edges(g: Graph) -> None:
        t = Task(action="file", name="task name")
        t.node_id = 0
        v = Variable(name="avar", version=0, value_version=0, scope_level=1)
        v.node_id = 1
        e = Keyword(keyword="args.path")
        g.add_node(t)
        g.add_node(v)
        g.add_edge(v, t, e)

        result = dump_graph(g)

        assert result == "CREATE " + ", \n".join(
            [dump_node(t, g), dump_node(v, g), dump_edge(e, v, t)]
        )
