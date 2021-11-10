from typing import Any

import pytest

from ansible_graph_extractor.models.edges import DEF, Keyword, ORDER, USE
from ansible_graph_extractor.models.graph import Graph
from ansible_graph_extractor.models.nodes import Expression, Literal, Node, Task, Variable
from ansible_graph_extractor.io.graphml import dump_graph, import_graph

from graph_matchers import assert_graphs_match, create_graph


@pytest.fixture
def g() -> Graph:
    return Graph('testrole', 'v1.0.0')


@pytest.fixture
def pop_g(g: Graph) -> Graph:
    return create_graph({
        't1': Task(action='file', name='task 1'),
        't2': Task(action='command', name='task 2'),
        'l1': Literal(type='str', value='echo "Hello"'),
        'l2': Literal(type='bool', value=False),
        'l3': Literal(type='int', value=0o777),
        'v': Variable(name='filepath', version=1),
        'e': Expression(expr='test/{{ filepath }}'),
        'v2': Variable(name='$1', version=1),
    }, [
        ('t1', 't2', ORDER),
        ('l1', 't2', Keyword(keyword='args')),
        ('l2', 't2', Keyword(keyword='changed_when')),
        ('l3', 't1', Keyword(keyword='args.mode')),
        ('v', 'e', USE),
        ('e', 'v2', DEF),
        ('v2', 't1', Keyword(keyword='args.path')),
    ])


def describe_export_graphml() -> None:

    def should_not_dump_empty_graph(g: Graph) -> None:
        result = dump_graph(g)

        assert not result

    def should_dump_graph(pop_g: Graph) -> None:
        result = dump_graph(pop_g)

        # Not checking the whole thing, if it serialises and deserialises
        # to an equivalent graph, it's OK.
        assert result


def describe_import_graphml() -> None:

    def should_import_graph(pop_g: Graph) -> None:
        graphml = dump_graph(pop_g)

        result = import_graph(graphml)

        assert_graphs_match(result, pop_g, ignore_graph_kws={'node_default', 'edge_default'})
