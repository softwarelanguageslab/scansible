# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import Literal, Protocol, cast

from itertools import product

import pytest
from _pytest.fixtures import FixtureRequest
from pytest_describe import behaves_like

from scansible.representations.pdg import representation as rep


class NodeFactory(Protocol):
    def __call__(self, loc: rep.NodeLocation) -> rep.Node: ...


# Shared behaviour for nodes
def a_node() -> None:
    def should_be_constructible(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation(file="test.yml", line=0, column=0))

        assert node is not None

    def should_not_be_hashable_before_node_id_is_set(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation(file="test.yml", line=0, column=0))

        with pytest.raises(Exception):
            _ = hash(node)

    def should_be_hashable_after_node_id_is_set(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation(file="test.yml", line=0, column=0))
        node.node_id = 0

        assert hash(node) is not None

    def should_support_equality(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation(file="test.yml", line=0, column=0))

        assert node == node

    def should_be_unique_if_different_location(factory: NodeFactory) -> None:
        node1 = factory(rep.NodeLocation(file="test.yml", line=0, column=0))
        node2 = factory(rep.NodeLocation(file="test.yml", line=1, column=0))

        assert node1 != node2

    def should_be_same_if_same_location(factory: NodeFactory) -> None:
        node1 = factory(rep.NodeLocation(file="test.yml", line=0, column=0))
        node2 = factory(rep.NodeLocation(file="test.yml", line=0, column=0))

        assert node1 == node2

    def should_have_id(factory: NodeFactory) -> None:
        node = factory(rep.NodeLocation(file="test.yml", line=0, column=0))

        assert isinstance(node.node_id, int)


@behaves_like(a_node)
def describe_task() -> None:
    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.Task(
            action="file", name="Ensure file exists", location=loc
        )

    @pytest.mark.parametrize("action", ["file", "debug", "homebrew"])
    def should_have_action(action: str) -> None:
        task = rep.Task(action=action, name="test")

        assert task.action == action

    @pytest.mark.parametrize("action", [None, 1, ["action"], ""])
    def should_reject_invalid_actions(action: object) -> None:
        with pytest.raises(ValueError):
            _ = rep.Task(action=action, name="test")  # pyright: ignore[reportArgumentType]

    @pytest.mark.parametrize("name", ["test", "ensure something", None])
    def should_have_name(name: str | None) -> None:
        task = rep.Task(action="file", name=name)

        assert task.name == name


@behaves_like(a_node)
def describe_variable() -> None:
    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.Variable(
            name="a_var", version=1, value_version=1, scope_level=1, location=loc
        )

    @pytest.mark.parametrize("name", ["test", "my_name", "a_var"])
    def should_have_name(name: str) -> None:
        var = rep.Variable(name=name, version=1, value_version=1, scope_level=1)

        assert var.name == name

    @pytest.mark.parametrize("name", [None, 1, ["name"], ""])
    def should_reject_invalid_names(name: object) -> None:
        with pytest.raises(ValueError):
            _ = rep.Variable(name=name, version=1, value_version=1, scope_level=1)  # pyright: ignore[reportArgumentType]


@behaves_like(a_node)
def describe_literal() -> None:
    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.ScalarLiteral(type="bool", value=True, location=loc)

    @pytest.mark.parametrize("type", ["bool", "str", "list"])
    def should_have_type(type: Literal["bool", "str", "list"]) -> None:
        lit = rep.ScalarLiteral(type=type, value=None)

        assert lit.type == type

    def should_reject_invalid_types() -> None:
        with pytest.raises(ValueError):
            _ = rep.ScalarLiteral(type="not_a_type", value=None)  # pyright: ignore[reportArgumentType]

    @pytest.mark.parametrize("value", [None, 1, "value", 1.0, False])
    def scalar_should_have_value(value: int | str | float | bool | None) -> None:
        _ = rep.ScalarLiteral(type="str", value=value)

    @pytest.mark.parametrize("value", [["value1", "value2"], {"value1": "value2"}])
    def scalar_should_reject_composite_values(
        value: list[str] | dict[str, str],
    ) -> None:
        with pytest.raises(ValueError):
            _ = rep.ScalarLiteral(type="str", value=value)  # pyright: ignore[reportArgumentType]


@behaves_like(a_node)
def describe_expression() -> None:
    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda loc: rep.Expression(expr="{{ template_expr }}", location=loc)

    @pytest.mark.parametrize("expr", ["something", "{{ something }}"])
    def should_have_expr(expr: str) -> None:
        exprNode = rep.Expression(expr=expr)

        assert exprNode.expr == expr

    @pytest.mark.parametrize("expr", [[], "", 1])
    def should_reject_invalid_expr(expr: object) -> None:
        with pytest.raises(ValueError):
            _ = rep.Expression(expr=expr)  # pyright: ignore[reportArgumentType]


def describe_construction() -> None:
    def should_construct() -> None:
        g = rep.Graph(role_name="me.role", role_version="1.0.0")

        assert g is not None

    @pytest.mark.parametrize("role_name", ["my.role", "your.other_role"])
    def should_have_role_name(role_name: str) -> None:
        g = rep.Graph(role_name=role_name, role_version="1.0.0")

        assert g.role_name == role_name

    @pytest.mark.parametrize("role_version", ["1.0.0", "HEAD", "1.2.3"])
    def should_have_role_version(role_version: str) -> None:
        g = rep.Graph(role_name="me.role", role_version=role_version)

        assert g.role_version == role_version


@pytest.fixture()
def g() -> rep.Graph:
    g = rep.Graph(role_name="test", role_version="HEAD")
    assert g.num_nodes == 0
    return g


def describe_add_node() -> None:
    def should_add_a_node(g: rep.Graph) -> None:
        n = rep.Task(action="file")
        g.add_node(n)

        assert g.num_nodes == 1
        assert g.nodes == [n]
        assert g.has_node(n)

    def should_add_multiple_nodes(g: rep.Graph) -> None:
        n1, n2 = rep.Task(action="file"), rep.Task(action="command")
        g.add_node(n1)
        g.add_node(n2)

        assert g.num_nodes == 2
        assert sorted(g.nodes, key=lambda t: t.node_id) == sorted(
            [n1, n2], key=lambda t: t.node_id
        )
        assert g.has_node(n1)
        assert g.has_node(n2)

    def should_not_add_the_same_node_twice(g: rep.Graph) -> None:
        n = rep.Task(action="file")
        g.add_node(n)
        g.add_node(n)

        assert g.num_nodes == 1
        assert g.has_node(n)

    def should_add_two_equivalent_nodes_with_different_locations(g: rep.Graph) -> None:
        n1, n2 = (
            rep.Task(
                action="file",
                location=rep.NodeLocation(file="test.yml", line=1, column=1),
            ),
            rep.Task(
                action="file",
                location=rep.NodeLocation(file="test.yml", line=5, column=1),
            ),
        )
        g.add_node(n1)
        g.add_node(n2)

        assert g.num_nodes == 2
        assert sorted(g.nodes, key=lambda t: t.node_id) == sorted(
            [n1, n2], key=lambda t: t.node_id
        )
        assert g.has_node(n1)
        assert g.has_node(n2)


def describe_add_nodes() -> None:
    def should_add_a_node(g: rep.Graph) -> None:
        n = rep.Task(action="file")
        g.add_nodes([n])

        assert g.num_nodes == 1
        assert g.nodes == [n]
        assert g.has_node(n)

    def should_add_multiple_nodes(g: rep.Graph) -> None:
        n1, n2 = rep.Task(action="file"), rep.Task(action="command")
        g.add_nodes([n1, n2])

        assert g.num_nodes == 2
        assert sorted(g.nodes, key=lambda t: t.node_id) == sorted(
            [n1, n2], key=lambda t: t.node_id
        )
        assert g.has_node(n1)
        assert g.has_node(n2)

    def should_not_add_the_same_node_twice(g: rep.Graph) -> None:
        n = rep.Task(action="file")
        g.add_nodes([n, n])

        assert g.num_nodes == 1
        assert g.has_node(n)

    def should_add_two_equivalent_nodes_with_different_location(g: rep.Graph) -> None:
        n1, n2 = (
            rep.Task(
                action="file",
                location=rep.NodeLocation(file="test.yml", line=1, column=1),
            ),
            rep.Task(
                action="file",
                location=rep.NodeLocation(file="test.yml", line=5, column=1),
            ),
        )
        g.add_nodes([n1, n2])

        assert g.num_nodes == 2
        assert sorted(g.nodes, key=lambda t: t.node_id) == sorted(
            [n1, n2], key=lambda t: t.node_id
        )
        assert g.has_node(n1)
        assert g.has_node(n2)

    def should_not_add_nodes_from_empty_list(g: rep.Graph) -> None:
        g.add_nodes([])

        assert g.num_nodes == 0


def describe_add_edge() -> None:
    def should_add_edge(g: rep.Graph) -> None:
        t1 = rep.Task(action="file")
        t2 = rep.Task(action="command")
        g.add_nodes([t1, t2])

        g.add_edge(t1, t2, rep.ORDER)

        assert g.num_edges == 1
        assert g.has_edge(t1, t2, rep.ORDER)

    def should_add_directed_edge(g: rep.Graph) -> None:
        t1 = rep.Task(action="file")
        t2 = rep.Task(action="command")
        g.add_nodes([t1, t2])

        g.add_edge(t1, t2, rep.ORDER)

        assert g.num_edges == 1
        assert g.has_edge(t1, t2, rep.ORDER)
        assert not g.has_edge(t2, t1, rep.ORDER)

    def should_not_add_multiple_edges_of_same_type(g: rep.Graph) -> None:
        t1 = rep.Task(action="file")
        t2 = rep.Task(action="command")
        g.add_nodes([t1, t2])

        g.add_edge(t1, t2, rep.ORDER)
        g.add_edge(t1, t2, rep.ORDER)

        assert g.num_edges == 1

    def should_allow_multiple_edges_of_different_types(g: rep.Graph) -> None:
        e = rep.Expression(expr="{{ test }}")
        t = rep.Task(action="command")
        g.add_nodes([e, t])

        g.add_edge(e, t, rep.Keyword(keyword="args.first"))
        g.add_edge(e, t, rep.Keyword(keyword="args.second"))

        assert g.num_edges == 2


def validated_edge() -> None:
    def should_accept_valid_edge(
        g: rep.Graph,
        valid_source_and_target: tuple[rep.Node, rep.Node],
        edge_type: rep.Edge,
    ) -> None:
        source, target = valid_source_and_target
        g.add_nodes([source, target])

        g.add_edge(source, target, edge_type)

        assert g.has_edge(source, target, edge_type)

    def should_reject_invalid_edge(
        g: rep.Graph,
        invalid_source_and_target: tuple[rep.Node, rep.Node],
        edge_type: rep.Edge,
    ) -> None:
        source, target = invalid_source_and_target
        g.add_nodes([source, target])

        with pytest.raises(TypeError):
            g.add_edge(source, target, edge_type)


@behaves_like(validated_edge)
def describe_order_edge() -> None:
    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.ORDER

    tsk1 = rep.Task(action="file")
    tsk2 = rep.Task(action="command")
    var = rep.Variable(name="test", version=1, value_version=1, scope_level=1)
    exp = rep.Expression(expr="{{ test }}")
    lit = rep.ScalarLiteral(type="str", value="test")

    @pytest.fixture(params=[(tsk1, tsk2)])
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param

    invalid_combos = list(product([tsk1, exp, var, lit], repeat=2))
    invalid_combos.remove((tsk1, tsk1))

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param


@behaves_like(validated_edge)
def describe_use_edge() -> None:
    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.USE

    tsk = rep.Task(action="file")
    var = rep.Variable(name="test", version=1, value_version=1, scope_level=1)
    exp = rep.Expression(expr="{{ test }}")
    lit = rep.ScalarLiteral(type="str", value="test")

    @pytest.fixture(params=[(var, exp)])
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param

    invalid_combos = list(product([tsk, var, exp, lit], repeat=2))
    invalid_combos.remove((var, exp))

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param


@behaves_like(validated_edge)
def describe_def_edge() -> None:
    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.DEF

    tsk = rep.Task(action="file")
    var = rep.Variable(name="test", version=1, value_version=1, scope_level=1)
    exp = rep.Expression(expr="{{ test }}")
    lit = rep.ScalarLiteral(type="str", value="test")

    valid = list(product([exp, lit, tsk, var], [var, exp]))

    @pytest.fixture(params=valid)
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param

    invalid_combos = list(product([tsk, var, exp, lit], repeat=2))
    for valid_combo in valid:
        invalid_combos.remove(valid_combo)

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param


@behaves_like(validated_edge)
def describe_kw_edge() -> None:
    @pytest.fixture()
    def edge_type() -> rep.Edge:
        return rep.Keyword(keyword="args.param")

    tsk = rep.Task(action="file")
    var = rep.Variable(name="test", version=1, value_version=1, scope_level=1)
    exp = rep.Expression(expr="{{ test }}")
    lit = rep.ScalarLiteral(type="str", value="test")

    valid = list(product([exp, lit, var], [tsk]))

    @pytest.fixture(params=valid)
    def valid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param

    invalid_combos = list(product([tsk, var, exp, lit], repeat=2))
    for valid_combo in valid:
        invalid_combos.remove(valid_combo)

    @pytest.fixture(params=invalid_combos)
    def invalid_source_and_target(request: FixtureRequest) -> tuple[rep.Node, rep.Node]:
        param = cast(tuple[rep.Node, rep.Node], request.param)
        for n in param:
            n.node_id = -1
        return param
