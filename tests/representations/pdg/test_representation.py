from typing import Any, Protocol

from itertools import chain, product

import pytest
from _pytest.fixtures import FixtureRequest
from pytest_describe import behaves_like

from scansible.representations.pdg import representation as rep


class NodeFactory(Protocol):

    def __call__(self, location: rep.NodeLocation) -> rep.Node:
        ...


# Shared behaviour for nodes
def a_node() -> None:

    def should_be_constructible(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation('test.yml', 0, 0))

        assert node is not None

    def should_be_hashable(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation('test.yml', 0, 0))

        assert hash(node) is not None

    def should_support_equality(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation('test.yml', 0, 0))

        assert node == node

    def should_be_unique_if_different_location(factory: NodeFactory) -> None:
        node1 = factory(rep.NodeLocation('test.yml', 0, 0))
        node2 = factory(rep.NodeLocation('test.yml', 1, 0))

        assert node1 != node2

    def should_be_same_if_same_location(factory: NodeFactory) -> None:
        node1 = factory(rep.NodeLocation('test.yml', 0, 0))
        node2 = factory(rep.NodeLocation('test.yml', 0, 0))

        assert node1 == node2

    def should_have_id(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation('test.yml', 0, 0))

        assert isinstance(node.node_id, int)


@behaves_like(a_node)
def describe_task() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.Task(action='file', name='Ensure file exists', location=loc)

    @pytest.mark.parametrize('action', ['file', 'debug', 'homebrew'])
    def should_have_action(action: str) -> None:
        task = rep.Task(action=action, name='test')

        assert task.action == action

    @pytest.mark.parametrize('action', [None, 1, ['action'], ''])
    def should_reject_invalid_actions(action: object) -> None:
        with pytest.raises(ValueError):
            rep.Task(action=action, name='test')  # type: ignore[arg-type]

    @pytest.mark.parametrize('name', ['test', 'ensure something', None])
    def should_have_name(name: str | None) -> None:
        task = rep.Task(action='file', name=name)

        assert task.name == name


@behaves_like(a_node)
def describe_variable() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.Variable(name='a_var', version=1, value_version=1, scope_level=1, location=loc)

    @pytest.mark.parametrize('name', ['test', 'my_name', 'a_var'])
    def should_have_name(name: str) -> None:
        var = rep.Variable(name=name, version=1, value_version=1, scope_level=1)

        assert var.name == name

    @pytest.mark.parametrize('name', [None, 1, ['name'], ''])
    def should_reject_invalid_names(name: object) -> None:
        with pytest.raises(ValueError):
            rep.Variable(name=name, version=1, value_version=1, scope_level=1)  # type: ignore[arg-type]


@behaves_like(a_node)
def describe_literal() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.Literal(type='bool', value=True, location=loc)

    @pytest.mark.parametrize('type', ['bool', 'str', 'list'])
    def should_have_type(type: str) -> None:
        lit = rep.Literal(type=type, value=None)  # type: ignore[arg-type]

        assert lit.type == type

    def should_reject_invalid_types() -> None:
        with pytest.raises(ValueError):
            rep.Literal(type='not_a_type', value=None)  # type: ignore[arg-type]

    @pytest.mark.parametrize('value', [None, 1, ['values'], 'value'])
    def should_have_value(value: object) -> None:
        lit = rep.Literal(type='str', value=value)


@behaves_like(a_node)
def describe_expression() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.Expression(expr='{{ template_expr }}', location=loc)

    @pytest.mark.parametrize('expr', ['something', '{{ something }}'])
    def should_have_expr(expr: str) -> None:
        exprNode = rep.Expression(expr=expr)

        assert exprNode.expr == expr

    @pytest.mark.parametrize('expr', [[], '', 1])
    def should_reject_invalid_expr(expr: object) -> None:
        with pytest.raises(ValueError):
            rep.Expression(expr=expr)  # type: ignore[arg-type]



def describe_construction() -> None:

    def should_construct() -> None:
        g = rep.Graph(role_name='me.role', role_version='1.0.0')

        assert g is not None

    @pytest.mark.parametrize('role_name', ['my.role', 'your.other_role'])
    def should_have_role_name(role_name: str) -> None:
        g = rep.Graph(role_name=role_name, role_version='1.0.0')

        assert g.role_name == role_name

    @pytest.mark.parametrize('role_version', ['1.0.0', 'HEAD', '1.2.3'])
    def should_have_role_version(role_version: str) -> None:
        g = rep.Graph(role_name='me.role', role_version=role_version)

        assert g.role_version == role_version

@pytest.fixture()
def g() -> rep.Graph:
    g = rep.Graph(role_name='test', role_version='HEAD')
    assert len(g) == 0
    return g

def describe_add_node() -> None:

    def should_add_a_node(g: rep.Graph) -> None:
        n = rep.Task(action='file')
        g.add_node(n)

        assert len(g) == 1
        assert next(iter(g)) is n
        assert n in g

    def should_add_multiple_nodes(g: rep.Graph) -> None:
        n1, n2 = rep.Task(action='file'), rep.Task(action='command')
        g.add_node(n1)
        g.add_node(n2)

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    def should_not_add_the_same_node_twice(g: rep.Graph) -> None:
        n = rep.Task(action='file')
        g.add_node(n)
        g.add_node(n)

        assert len(g) == 1
        assert n in g

    def should_add_two_equivalent_nodes_with_different_locations(g: rep.Graph) -> None:
        n1, n2 = rep.Task(action='file', location=rep.NodeLocation('test.yml', 1, 1)), rep.Task(action='file', location=rep.NodeLocation('test.yml', 5, 1))
        g.add_node(n1)
        g.add_node(n2)

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    @pytest.mark.parametrize('wrong_node', [1, False, None, [], 'str'])
    def should_only_accept_nodes(g: rep.Graph, wrong_node: object) -> None:
        with pytest.raises(TypeError):
            g.add_node(wrong_node)  # type: ignore[arg-type]

def describe_add_nodes_from() -> None:

    def should_add_a_node(g: rep.Graph) -> None:
        n = rep.Task(action='file')
        g.add_nodes_from([n])

        assert len(g) == 1
        assert next(iter(g)) is n
        assert n in g

    def should_add_multiple_nodes(g: rep.Graph) -> None:
        n1, n2 = rep.Task(action='file'), rep.Task(action='command')
        g.add_nodes_from([n1, n2])

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    def should_not_add_the_same_node_twice(g: rep.Graph) -> None:
        n = rep.Task(action='file')
        g.add_nodes_from([n, n])

        assert len(g) == 1
        assert n in g

    def should_add_two_equivalent_nodes_with_different_location(g: rep.Graph) -> None:
        n1, n2 = rep.Task(action='file', location=rep.NodeLocation('test.yml', 1, 1)), rep.Task(action='file', location=rep.NodeLocation('test.yml', 5, 1))
        g.add_nodes_from([n1, n2])

        assert len(g) == 2
        assert set(iter(g)) == {n1, n2}
        assert n1 in g
        assert n2 in g

    def should_not_add_nodes_from_empty_list(g: rep.Graph) -> None:
        g.add_nodes_from([])

        assert not g

    @pytest.mark.parametrize('wrong_node', [1, False, None, [], 'str'])
    def should_only_accept_nodes(g: rep.Graph, wrong_node: object) -> None:
        with pytest.raises(TypeError):
            g.add_nodes_from([wrong_node])  # type: ignore[list-item]


def describe_add_edge() -> None:

    def should_add_edge(g: rep.Graph) -> None:
        t1 = rep.Task(action='file')
        t2 = rep.Task(action='command')
        g.add_nodes_from([t1, t2])

        g.add_edge(t1, t2, rep.ORDER)

        assert g.number_of_edges() == 1
        assert g.has_edge(t1, t2)
        assert g[t1][t2][0]['type'] is rep.ORDER

    def should_add_directed_edge(g: rep.Graph) -> None:
        t1 = rep.Task(action='file')
        t2 = rep.Task(action='command')
        g.add_nodes_from([t1, t2])

        g.add_edge(t1, t2, rep.ORDER)

        assert g.number_of_edges() == 1
        assert g.has_edge(t1, t2)
        assert not g.has_edge(t2, t1)
        assert g[t1][t2][0]['type'] is rep.ORDER

    def should_not_add_multiple_edges_of_same_type(g: rep.Graph) -> None:
        t1 = rep.Task(action='file')
        t2 = rep.Task(action='command')
        g.add_nodes_from([t1, t2])

        g.add_edge(t1, t2, rep.ORDER)
        g.add_edge(t1, t2, rep.ORDER)

        assert g.number_of_edges() == 1

    def should_allow_multiple_edges_of_different_types(g: rep.Graph) -> None:
        e = rep.Expression(expr='{{ test }}')
        t = rep.Task(action='command')
        g.add_nodes_from([e, t])

        g.add_edge(e, t, rep.Keyword(keyword='args.first'))
        g.add_edge(e, t, rep.Keyword(keyword='args.second'))

        assert g.number_of_edges() == 2


def validated_edge() -> None:

    def should_accept_valid_edge(
            g: rep.Graph, valid_source_and_target: tuple[rep.Node, rep.Node],
            edge_type: rep.Edge
    ) -> None:
        source, target = valid_source_and_target
        g.add_nodes_from([source, target])

        g.add_edge(source, target, edge_type)

        assert g.has_edge(source, target)

    def should_reject_invalid_edge(
            g: rep.Graph, invalid_source_and_target: tuple[rep.Node, rep.Node],
            edge_type: rep.Edge
    ) -> None:
        source, target = invalid_source_and_target
        g.add_nodes_from([source, target])

        with pytest.raises(TypeError):
            g.add_edge(source, target, edge_type)

@behaves_like(validated_edge)
def describe_order_edge() -> None:

    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.ORDER

    t1 = rep.Task(action='file')
    t2 = rep.Task(action='command')
    v = rep.Variable(name='test', version=1, value_version=1, scope_level=1)
    e = rep.Expression(expr='{{ test }}')
    l = rep.Literal(type='str', value='test')

    @pytest.fixture(params=[(t1, t2)])
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]

    invalid_combos = set(product([t1, e, v, l], repeat=2)) - {(t1, t1)}

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]


@behaves_like(validated_edge)
def describe_use_edge() -> None:

    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.USE

    t = rep.Task(action='file')
    v = rep.Variable(name='test', version=1, value_version=1, scope_level=1)
    e = rep.Expression(expr='{{ test }}')
    l = rep.Literal(type='str', value='test', node_id=4)

    @pytest.fixture(params=[(v, e)])
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]

    invalid_combos = set(product([t, v, e, l], repeat=2)) - {(v, e)}

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]


@behaves_like(validated_edge)
def describe_def_edge() -> None:

    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.DEF

    t = rep.Task(action='file')
    v = rep.Variable(name='test', version=1, value_version=1, scope_level=1)
    e = rep.Expression(expr='{{ test }}')
    l = rep.Literal(type='str', value='test')

    valid = set(product([e, l, t, v], [v]))
    @pytest.fixture(params=valid)
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]

    invalid_combos = set(product([t, v, e, l], repeat=2)) - valid

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]


@behaves_like(validated_edge)
def describe_kw_edge() -> None:

    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.Keyword(keyword='args.param')

    t = rep.Task(action='file')
    v = rep.Variable(name='test', version=1, value_version=1, scope_level=1)
    e = rep.Expression(expr='{{ test }}')
    l = rep.Literal(type='str', value='test')

    valid = set(product([e, l, v], [t]))
    @pytest.fixture(params=valid)
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]

    invalid_combos = set(product([t, v, e, l], repeat=2)) - valid

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        return request.param  # type: ignore[no-any-return]
