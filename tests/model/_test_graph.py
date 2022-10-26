from typing import Any

from itertools import chain, product

import pytest
from pytest_describe import behaves_like

from scansible.models.edges import DEF, ORDER, USE, Edge, Keyword
from scansible.models.graph import Graph
from scansible.models.nodes import Expression, Literal, Node, Task, Variable


def describe_construction() -> None:

    def should_construct() -> None:
        g = Graph(role_name='me.role', role_version='1.0.0')

        assert g is not None

    @pytest.mark.parametrize('role_name', ['my.role', 'your.other_role'])
    def should_have_role_name(role_name: str) -> None:
        g = Graph(role_name=role_name, role_version='1.0.0')

        assert g.role_name == role_name

    @pytest.mark.parametrize('role_version', ['1.0.0', 'HEAD', '1.2.3'])
    def should_have_role_version(role_version: str) -> None:
        g = Graph(role_name='me.role', role_version=role_version)

        assert g.role_version == role_version

@pytest.fixture()
def g() -> Graph:
    g = Graph(role_name='test', role_version='HEAD')
    assert len(g) == 0
    return g

def describe_add_node() -> None:

    def should_add_a_node(g: Graph) -> None:
        n = Task(action='file')
        g.add_node(n)

        assert len(g) == 1
        assert next(iter(g)) is n
        assert n in g

    def should_add_multiple_nodes(g: Graph) -> None:
        n1, n2 = Task(action='file'), Task(action='command')
        g.add_node(n1)
        g.add_node(n2)

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    def should_not_add_the_same_node_twice(g: Graph) -> None:
        n = Task(action='file')
        g.add_node(n)
        g.add_node(n)

        assert len(g) == 1
        assert n in g

    def should_add_two_equivalent_nodes(g: Graph) -> None:
        n1, n2 = Task(action='file'), Task(action='file')
        g.add_node(n1)
        g.add_node(n2)

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    @pytest.mark.parametrize('wrong_node', [1, False, None, [], 'str'])
    def should_only_accept_nodes(g: Graph, wrong_node: Any) -> None:
        with pytest.raises(TypeError):
            g.add_node(wrong_node)

def describe_add_nodes_from() -> None:

    def should_add_a_node(g: Graph) -> None:
        n = Task(action='file')
        g.add_nodes_from([n])

        assert len(g) == 1
        assert next(iter(g)) is n
        assert n in g

    def should_add_multiple_nodes(g: Graph) -> None:
        n1, n2 = Task(action='file'), Task(action='command')
        g.add_nodes_from([n1, n2])

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    def should_not_add_the_same_node_twice(g: Graph) -> None:
        n = Task(action='file')
        g.add_nodes_from([n, n])

        assert len(g) == 1
        assert n in g

    def should_add_two_equivalent_nodes(g: Graph) -> None:
        n1, n2 = Task(action='file'), Task(action='file')
        g.add_nodes_from([n1, n2])

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    def should_not_add_nodes_from_empty_list(g: Graph) -> None:
        g.add_nodes_from([])

        assert not g

    @pytest.mark.parametrize('wrong_node', [1, False, None, [], 'str'])
    def should_only_accept_nodes(g: Graph, wrong_node: Any) -> None:
        with pytest.raises(TypeError):
            g.add_nodes_from([wrong_node])


def describe_add_edge() -> None:

    def should_add_edge(g: Graph) -> None:
        t1 = Task(action='file')
        t2 = Task(action='command')
        g.add_nodes_from([t1, t2])

        g.add_edge(t1, t2, ORDER)

        assert g.number_of_edges() == 1
        assert g.has_edge(t1, t2)
        assert g[t1][t2][0]['type'] is ORDER

    def should_add_directed_edge(g: Graph) -> None:
        t1 = Task(action='file')
        t2 = Task(action='command')
        g.add_nodes_from([t1, t2])

        g.add_edge(t1, t2, ORDER)

        assert g.number_of_edges() == 1
        assert g.has_edge(t1, t2)
        assert not g.has_edge(t2, t1)
        assert g[t1][t2][0]['type'] is ORDER

    def should_not_add_multiple_edges_of_same_type(g: Graph) -> None:
        t1 = Task(action='file')
        t2 = Task(action='command')
        g.add_nodes_from([t1, t2])

        g.add_edge(t1, t2, ORDER)
        g.add_edge(t1, t2, ORDER)

        assert g.number_of_edges() == 1

    def should_allow_multiple_edges_of_different_types(g: Graph) -> None:
        e = Expression(expr='{{ test }}')
        t = Task(action='command')
        g.add_nodes_from([e, t])

        g.add_edge(e, t, Keyword(keyword='args.first'))
        g.add_edge(e, t, Keyword(keyword='args.second'))

        assert g.number_of_edges() == 2


def validated_edge() -> None:

    def should_accept_valid_edge(
            g: Graph, valid_source_and_target: tuple[Node, Node],
            edge_type: Edge
    ) -> None:
        source, target = valid_source_and_target
        g.add_nodes_from([source, target])

        g.add_edge(source, target, edge_type)

        assert g.has_edge(source, target)

    def should_reject_invalid_edge(
            g: Graph, invalid_source_and_target: tuple[Node, Node],
            edge_type: Edge
    ) -> None:
        source, target = invalid_source_and_target
        g.add_nodes_from([source, target])

        with pytest.raises(TypeError):
            g.add_edge(source, target, edge_type)

@behaves_like(validated_edge)
def describe_order_edge() -> None:

    @pytest.fixture()
    def edge_type() -> Edge:
        return ORDER

    t1 = Task(action='file', node_id=1, location='')
    t2 = Task(action='command', node_id=2, location='')
    v = Variable(name='test', version=1, value_version=1, scope_level=1, node_id=3, location='')
    e = Expression(expr='{{ test }}', node_id=4, location='')
    l = Literal(type='str', value='test', node_id=5, location='')

    @pytest.fixture(params=[(t1, t2)])
    def valid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param

    invalid_combos = set(product([t1, e, v, l], repeat=2)) - {(t1, t1)}

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param


@behaves_like(validated_edge)
def describe_use_edge() -> None:

    @pytest.fixture()
    def edge_type() -> Edge:
        return USE

    t = Task(action='file', node_id=1, location='')
    v = Variable(name='test', version=1, value_version=1, scope_level=1, node_id=2, location='')
    e = Expression(expr='{{ test }}', node_id=3, location='')
    l = Literal(type='str', value='test', node_id=4, location='')

    @pytest.fixture(params=[(v, e)])
    def valid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param

    invalid_combos = set(product([t, v, e, l], repeat=2)) - {(v, e)}

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param


@behaves_like(validated_edge)
def describe_def_edge() -> None:

    @pytest.fixture()
    def edge_type() -> Edge:
        return DEF

    t = Task(action='file', node_id=1, location='')
    v = Variable(name='test', version=1, value_version=1, scope_level=1, node_id=2, location='')
    e = Expression(expr='{{ test }}', node_id=3, location='')
    l = Literal(type='str', value='test', node_id=4, location='')

    valid = set(product([e, l, t, v], [v]))
    @pytest.fixture(params=valid)
    def valid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param

    invalid_combos = set(product([t, v, e, l], repeat=2)) - valid

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param


@behaves_like(validated_edge)
def describe_kw_edge() -> None:

    @pytest.fixture()
    def edge_type() -> Edge:
        return Keyword(keyword='args.param')

    t = Task(action='file', node_id=1, location='')
    v = Variable(name='test', version=1, value_version=1, scope_level=1, node_id=2, location='')
    e = Expression(expr='{{ test }}', node_id=3, location='')
    l = Literal(type='str', value='test', node_id=4, location='')

    valid = set(product([e, l, v], [t]))
    @pytest.fixture(params=valid)
    def valid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param

    invalid_combos = set(product([t, v, e, l], repeat=2)) - valid

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: Any) -> tuple[Node, Node]:
        return request.param
