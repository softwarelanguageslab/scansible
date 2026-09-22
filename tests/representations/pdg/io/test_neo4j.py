# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import Literal as LiteralT

import pytest

from scansible.pdg import (
    DEF,
    ORDER,
    USE,
    Expression,
    Graph,
    Keyword,
    Node,
    NodeLocation,
    ScalarLiteral,
    Task,
    Variable,
)
from scansible.pdg.io.neo4j import dump_edge, dump_graph, dump_node
from scansible.utils import LineColumn


@pytest.fixture
def g() -> Graph:
    return Graph()


def describe_dump_node():
    def should_dump_expression():
        e = Expression(expr="{{ test }}")
        e.node_id = 0

        result = dump_node(e)

        assert (
            result
            == '(n0:Expression { expr: "{{ test }}", impure_components: "[]", location: null, node_id: 0 })'
        )

    def should_dump_variable():
        v = Variable(name="test", version=0, value_version=0, scope_level=1)
        v.node_id = 0

        result = dump_node(v)

        assert (
            result
            == '(n0:Variable { location: null, name: "test", node_id: 0, scope_level: 1, shadows: null, value_version: 0, version: 0 })'
        )

    def should_dump_task():
        t = Task(action="file", name="task name")
        t.node_id = 0

        result = dump_node(t)

        assert (
            result
            == '(n0:Task { action: "file", location: null, name: "task name", node_id: 0 })'
        )

    def should_dump_task_with_location():
        t = Task(
            action="file",
            name="task name",
            location=NodeLocation(
                path="test.yml", start=LineColumn(1, 10), end=LineColumn(1, 10)
            ),
        )
        t.node_id = 0

        result = dump_node(t)

        assert (
            result
            == '(n0:Task { action: "file", location: "{\\"path\\": \\"test.yml\\", \\"start\\": [1, 10], \\"end\\": [1, 10], \\"includer_location\\": null}", name: "task name", node_id: 0 })'
        )

    def should_dump_literal_string():
        l = ScalarLiteral(type="str", value="literal value")
        l.node_id = 0

        result = dump_node(l)

        assert (
            result
            == '(n0:ScalarLiteral { location: null, node_id: 0, type: "str", value: "literal value" })'
        )

    @pytest.mark.parametrize(
        ("type_", "value"),
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
        type_: LiteralT["int", "float", "bool"], value: float | bool
    ):
        l = ScalarLiteral(type=type_, value=value)
        l.node_id = 0

        result = dump_node(l)

        assert (
            result
            == f'(n0:ScalarLiteral {{ location: null, node_id: 0, type: "{type_}", value: {str(value).lower()} }})'
        )


def describe_dump_edge():
    def should_dump_order_edge():
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = ORDER

        result = dump_edge(e, n1, n2)

        assert result == "(n1)-[:ORDER { back: false, transitive: false }]->(n2)"

    def should_dump_def_edge():
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = DEF

        result = dump_edge(e, n1, n2)

        assert result == "(n1)-[:DEF]->(n2)"

    def should_dump_use_edge():
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = USE

        result = dump_edge(e, n1, n2)

        assert result == "(n1)-[:USE]->(n2)"

    def should_dump_keyword_edge():
        n1, n2 = Node(), Node()
        n1.node_id = 1
        n2.node_id = 2
        e = Keyword(keyword="the.keyword")

        result = dump_edge(e, n1, n2)

        assert result == '(n1)-[:KEYWORD { keyword: "the.keyword" }]->(n2)'


def describe_dump_graph():
    def should_return_empty_query_for_empty_graph(g: Graph):
        result = dump_graph(g)

        assert not result

    def should_return_query_for_graph_with_single_node(g: Graph):
        t = Task(action="file", name="task name")
        g.add_node(t)

        result = dump_graph(g)

        assert result == "CREATE " + dump_node(t)

    def should_return_query_for_graph_with_multiple_nodes_without_edges(g: Graph):
        t = Task(action="file", name="task name")
        v = Variable(name="avar", version=0, value_version=0, scope_level=1)
        g.add_node(t)
        g.add_node(v)

        result = dump_graph(g)

        assert result == "CREATE " + ", \n".join([dump_node(t), dump_node(v)])

    def should_return_query_for_graph_with_multiple_nodes_with_edges(g: Graph):
        t = Task(action="file", name="task name")
        v = Variable(name="avar", version=0, value_version=0, scope_level=1)
        e = Keyword(keyword="args.path")
        g.add_node(t)
        g.add_node(v)
        g.add_edge(v, t, e)

        result = dump_graph(g)

        assert result == "CREATE " + ", \n".join(
            [dump_node(t), dump_node(v), dump_edge(e, v, t)]
        )
