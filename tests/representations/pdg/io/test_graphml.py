from __future__ import annotations

from typing import Any

import pytest

from scansible.representations.pdg import representation as rep
from scansible.representations.pdg.io.graphml import dump_graph, import_graph
from test_utils.graph_matchers import assert_graphs_match, create_graph


@pytest.fixture
def g() -> rep.Graph:
    return rep.Graph("testrole", "v1.0.0")


@pytest.fixture
def pop_g(g: rep.Graph) -> rep.Graph:
    return create_graph(
        {
            "t1": rep.Task(
                action="file", name="task 1", location=rep.NodeLocation("x.yml", 1, 1)
            ),
            "t2": rep.Task(
                action="command",
                name="task 2",
                location=rep.NodeLocation("x.yml", 5, 1),
            ),
            "l1": rep.Literal(
                type="str",
                value='echo "Hello"',
                location=rep.NodeLocation("x.yml", 2, 5),
            ),
            "l2": rep.Literal(
                type="bool", value=False, location=rep.NodeLocation("x.yml", 3, 5)
            ),
            "l3": rep.Literal(
                type="int", value=0o777, location=rep.NodeLocation("x.yml", 7, 123)
            ),
            "v": rep.Variable(
                name="filepath",
                version=0,
                value_version=0,
                scope_level=1,
                location=rep.NodeLocation("x.yml", 4, 2),
            ),
            "e": rep.Expression(
                expr="test/{{ filepath }}", location=rep.NodeLocation("x.yml", 10, 43)
            ),
            "v2": rep.Variable(
                name="$1",
                version=0,
                value_version=0,
                scope_level=1,
                location=rep.NodeLocation("x.yml", 123, 343),
            ),
        },
        [
            ("t1", "t2", rep.ORDER),
            ("l1", "t2", rep.Keyword(keyword="args")),
            ("l2", "t2", rep.Keyword(keyword="changed_when")),
            ("l3", "t1", rep.Keyword(keyword="args.mode")),
            ("v", "e", rep.USE),
            ("e", "v2", rep.DEF),
            ("v2", "t1", rep.Keyword(keyword="args.path")),
        ],
    )


def describe_export_graphml() -> None:
    def should_not_dump_empty_graph(g: rep.Graph) -> None:
        result = dump_graph(g)

        assert not result

    def should_dump_graph(pop_g: rep.Graph) -> None:
        result = dump_graph(pop_g)

        # Not checking the whole thing, if it serialises and deserialises
        # to an equivalent graph, it's OK.
        assert result


def describe_import_graphml() -> None:
    def should_import_graph(pop_g: rep.Graph) -> None:
        graphml = dump_graph(pop_g)

        result = import_graph(graphml, "test", "test")

        assert_graphs_match(
            result,
            pop_g,
            ignore_graph_kws={"node_default", "edge_default"},
            match_locations=True,
        )
