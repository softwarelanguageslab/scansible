from __future__ import annotations

from typing import TYPE_CHECKING, final, override

import pytest
from loguru import logger

from scansible.checks.security.db import GraphDatabase
from scansible.checks.security.rules.base import GraphDBRule, RuleQuery
from scansible.pdg import (
    DEF,
    Expression,
    Graph,
    IntermediateValue,
    Node,
    NodeLocation,
    ScalarLiteral,
    Variable,
)
from scansible.utils.location import LineColumn

if TYPE_CHECKING:
    from collections.abc import Iterator


@final
class _StubRule(GraphDBRule):
    code = "TEST"
    description = "stub"

    @property
    @override
    def query(self) -> RuleQuery:
        return "", {}

    @override
    def describe(self, label: str) -> str:
        return label


def _loc(line: int) -> NodeLocation:
    return NodeLocation(
        path="pb.yml", start=LineColumn(line, 1), end=LineColumn(line, 2)
    )


def _variable(name: str, line: int) -> Variable:
    return Variable(
        name=name, version=0, value_version=0, scope_level=0, location=_loc(line)
    )


def _literal(value: str) -> ScalarLiteral:
    return ScalarLiteral(type="str", value=value)


def _get_location(graph: Graph, node: Node) -> NodeLocation:
    with GraphDatabase(graph) as db:
        return _StubRule()._get_location(db, node.node_id)  # noqa: SLF001  # pyright: ignore[reportPrivateUsage]


def _capture_errors() -> tuple[list[str], int]:
    messages: list[str] = []
    handler_id = logger.add(lambda m: messages.append(str(m)), level="ERROR")
    return messages, handler_id


@pytest.fixture
def errors() -> Iterator[list[str]]:
    messages, handler_id = _capture_errors()
    yield messages
    logger.remove(handler_id)


def test_returns_real_location_unchanged() -> None:
    graph = Graph()
    var = _variable("a", 3)
    graph.add_node(var)

    assert _get_location(graph, var) == _loc(3)


def test_follows_single_assignment_from_synthetic_node() -> None:
    graph = Graph()
    lit, var = _literal("x"), _variable("a", 5)
    graph.add_nodes([lit, var])
    graph.add_edge(lit, var, DEF)

    assert _get_location(graph, lit) == _loc(5)


def test_follows_chain_of_synthetic_nodes() -> None:
    graph = Graph()
    expr = Expression(expr="{{ b }}")
    iv = IntermediateValue(identifier=0)
    var = _variable("a", 7)
    graph.add_nodes([expr, iv, var])
    graph.add_edge(expr, iv, DEF)
    graph.add_edge(iv, var, DEF)

    assert _get_location(graph, expr) == _loc(7)


def test_unassigned_synthetic_node_stays_synthetic_and_logs(
    errors: list[str],
) -> None:
    graph = Graph()
    lit = _literal("x")
    graph.add_node(lit)

    assert _get_location(graph, lit).is_synthetic
    assert any("is not assigned" in m for m in errors)


def test_multiply_assigned_synthetic_node_stays_synthetic_and_logs(
    errors: list[str],
) -> None:
    graph = Graph()
    lit, var1, var2 = _literal("x"), _variable("a", 5), _variable("b", 6)
    graph.add_nodes([lit, var1, var2])
    graph.add_edge(lit, var1, DEF)
    graph.add_edge(lit, var2, DEF)

    assert _get_location(graph, lit).is_synthetic
    assert any("assigned multiple times" in m for m in errors)
