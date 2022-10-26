from typing import Any, Optional, Protocol

import pytest
from pytest_describe import behaves_like

from scansible.models.nodes import Expression, Literal, Node, Task, Variable

class NodeFactory(Protocol):

    def __call__(self) -> Node:
        ...


# Shared behaviour for nodes
def a_node() -> None:

    def should_be_constructible(factory: NodeFactory) -> None:
        node = factory()

        assert node is not None

    def should_be_hashable(factory: NodeFactory) -> None:
        node = factory()

        assert hash(node) is not None

    def should_support_equality(factory: NodeFactory) -> None:
        node = factory()

        assert node == node

    def should_be_unique(factory: NodeFactory) -> None:
        node1 = factory()
        node2 = factory()

        assert node1 != node2

    def should_have_id(factory: NodeFactory) -> None:
        node = factory()

        assert isinstance(node.node_id, int)


@behaves_like(a_node)
def describe_task() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda: Task(action='file', name='Ensure file exists')

    @pytest.mark.parametrize('action', ['file', 'debug', 'homebrew'])
    def should_have_action(action: str) -> None:
        task = Task(action=action, name='test')

        assert task.action == action

    @pytest.mark.parametrize('action', [None, 1, ['action'], ''])
    def should_reject_invalid_actions(action: Any) -> None:
        with pytest.raises(ValueError):
            task = Task(action=action, name='test')

    @pytest.mark.parametrize('name', ['test', 'ensure something', None])
    def should_have_name(name: Optional[str]) -> None:
        task = Task(action='file', name=name)

        assert task.name == name


@behaves_like(a_node)
def describe_variable() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda: Variable(name='a_var', version=1)

    @pytest.mark.parametrize('name', ['test', 'my_name', 'a_var'])
    def should_have_name(name: str) -> None:
        var = Variable(name=name, version=1)

        assert var.name == name

    @pytest.mark.parametrize('name', [None, 1, ['name'], ''])
    def should_reject_invalid_names(name: Any) -> None:
        with pytest.raises(ValueError):
            task = Variable(name=name, version=1)


@behaves_like(a_node)
def describe_literal() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda: Literal(type='bool', value=True)

    @pytest.mark.parametrize('type', ['bool', 'str', 'list'])
    def should_have_type(type: str) -> None:
        lit = Literal(type=type, value=None)

        assert lit.type == type

    def should_reject_invalid_types() -> None:
        with pytest.raises(ValueError):
            lit = Literal(type='not_a_type', value=None)

    @pytest.mark.parametrize('value', [None, 1, ['values'], 'value'])
    def should_have_value(value: Any) -> None:
        lit = Literal(type='str', value=value)


@behaves_like(a_node)
def describe_expression() -> None:

    @pytest.fixture()
    def factory() -> NodeFactory:
        return lambda: Expression(expr='{{ template_expr }}')

    @pytest.mark.parametrize('expr', ['something', '{{ something }}'])
    def should_have_expr(expr: str) -> None:
        exprNode = Expression(expr=expr)

        assert exprNode.expr == expr

    @pytest.mark.parametrize('expr', [[], '', 1])
    def should_reject_invalid_expr(expr: Any) -> None:
        with pytest.raises(ValueError):
            exprNode = Expression(expr=expr)
