# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import Any, Literal, cast

from collections.abc import Callable
from pathlib import Path

import pytest
from graph_matchers import (  # pyright: ignore[reportImplicitRelativeImport]
    assert_graphs_match,
    create_graph,
)
from pytest_mock import MockerFixture

from scansible.representations import ast
from scansible.representations.pdg import (
    DEF,
    CompositeLiteral,
    Expression,
    Graph,
    Input,
    IntermediateValue,
    ScalarLiteral,
    Variable,
)
from scansible.representations.pdg.extractor.context import ExtractionContext
from scansible.representations.pdg.extractor.expressions import (
    EnvironmentType,
    VarContext,
)
from scansible.representations.pdg.representation import Composition

ContextCreator = Callable[[], tuple[VarContext, Graph]]


@pytest.fixture
def create_context(g: Graph, mocker: MockerFixture, tmp_path: Path) -> ContextCreator:
    return lambda: (
        ExtractionContext(
            g,
            mocker.Mock(
                **cast(  # pyright: ignore[reportAny]
                    dict[str, Any],  # pyright: ignore[reportExplicitAny]
                    {
                        "path": tmp_path,
                        "root.main_tasks_file.path": Path("tasks/main.yml"),
                    },
                )
            ),
            mocker.Mock(),
            lenient=True,
        ).vars,
        g,
    )


# Shorthands to construct AST nodes
strlit = ast.StrLiteral
intlit = ast.IntLiteral
boollit = ast.BoolLiteral
expr = ast.Expression.model_validate
ident = ast.Identifier


def describe_evaluating_expressions():
    @pytest.mark.parametrize(
        ("expr", "type_"),
        [
            (strlit("hello"), "str"),
            (intlit(1), "int"),
            (boollit(True), "bool"),  # noqa: FBT003
            (strlit("yes"), "str"),
        ],
    )
    def should_build_scalar_literal(
        expr: ast.ScalarLiteral, type_: Literal["str"], create_context: ContextCreator
    ):
        ctx, g = create_context()
        actual_value = bool(expr) if isinstance(expr, ast.BoolLiteral) else expr

        _ = ctx.build_expression(expr)

        assert_graphs_match(
            g, create_graph({"lit": ScalarLiteral(type=type_, value=actual_value)}, [])
        )

    def should_build_seq_literal(create_context: ContextCreator):
        expr = ast.SeqLiteral([strlit("hello"), strlit("world")])
        ctx, g = create_context()

        _ = ctx.build_expression(expr)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": CompositeLiteral(type="list"),
                    "e1": ScalarLiteral(type="str", value="hello"),
                    "e2": ScalarLiteral(type="str", value="world"),
                },
                [
                    ("e1", "lit", Composition(index="0")),
                    ("e2", "lit", Composition(index="1")),
                ],
            ),
        )

    def should_build_map_literal(create_context: ContextCreator):
        expr = ast.MapLiteral[ast.ScalarLiteral, ast.AnyExpression](
            [(strlit("hello"), strlit("world")), (strlit("key"), strlit("value"))]
        )
        ctx, g = create_context()

        _ = ctx.build_expression(expr)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": CompositeLiteral(type="dict"),
                    "world": ScalarLiteral(type="str", value="world"),
                    "value": ScalarLiteral(type="str", value="value"),
                },
                [
                    ("world", "lit", Composition(index="hello")),
                    ("value", "lit", Composition(index="key")),
                ],
            ),
        )

    @pytest.mark.parametrize(
        "expression",
        [
            "{{ 1 + 1 }}",
            '{{ "/etc/tzinfo" | basename }}',
            '{{ lookup("indexed_items", [1,2,3]) }}',
            "{{ [1,2,3] | first }}",
            "The time is {{ now() }}",
            '{{ "/etc/tzinfo" is file }}',
            '{{ lookup("pipe", "echo Hello World") }}',
            "{{ [1,2,3] | random }}",
        ],
    )
    def should_build_standalone_expression(
        expression: str, create_context: ContextCreator
    ):
        ctx, g = create_context()

        _ = ctx.build_expression(expr(expression))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e": Expression(expr=expression),
                    "iv": IntermediateValue(identifier=1),
                },
                [("e", "iv", DEF)],
            ),
        )

    def should_build_expression_with_dependencies(create_context: ContextCreator):
        ctx, g = create_context()
        ctx.define_lazy_variable(
            ident("test"), EnvironmentType.CLI_VALUES, strlit("hello world")
        )
        e = expr("Value is {{ test }}")

        _ = ctx.build_expression(e)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": ScalarLiteral(type="str", value="hello world"),
                    "var": Variable(
                        name="test",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "e": Expression(expr=e.raw),
                    "iv": IntermediateValue(identifier=1),
                },
                [("e", "iv", DEF), ("lit", "var", DEF), ("var", "e", Input())],
            ),
        )

    def should_build_expression_with_complex_dependencies(
        create_context: ContextCreator,
    ):
        ctx, g = create_context()
        ctx.define_lazy_variable(
            ident("test"), EnvironmentType.CLI_VALUES, expr("{{ 1 + other }}")
        )
        ctx.define_lazy_variable(ident("other"), EnvironmentType.CLI_VALUES, intlit(2))

        e = expr("Value is {{ test }}")

        _ = ctx.build_expression(e)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": ScalarLiteral(type="int", value=2),
                    "other": Variable(
                        name="other",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "test_e": Expression(expr="{{ 1 + other }}"),
                    "test_iv": IntermediateValue(identifier=1),
                    "test": Variable(
                        name="test",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "e": Expression(expr=e.raw),
                    "iv": IntermediateValue(identifier=2),
                },
                [
                    ("lit", "other", DEF),
                    ("other", "test_e", Input()),
                    ("test_e", "test_iv", DEF),
                    ("test_iv", "test", DEF),
                    ("test", "e", Input()),
                    ("e", "iv", DEF),
                ],
            ),
        )

    def should_build_seq_literal_with_expression(create_context: ContextCreator):
        seq = ast.SeqLiteral([strlit("hello"), expr("{{ 1 + 1 }}")])
        ctx, g = create_context()

        _ = ctx.build_expression(seq)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": CompositeLiteral(type="list"),
                    "e1": ScalarLiteral(type="str", value="hello"),
                    "expr": Expression(expr="{{ 1 + 1 }}"),
                    "e2": IntermediateValue(identifier=1),
                },
                [
                    ("e1", "lit", Composition(index="0")),
                    ("e2", "lit", Composition(index="1")),
                    ("expr", "e2", DEF),
                ],
            ),
        )


def describe_reevaluating_expressions():
    @pytest.mark.parametrize(
        ("expr", "type_"),
        [
            (strlit("hello"), "str"),
            (intlit(1), "int"),
            (boollit(True), "bool"),  # noqa: FBT003
            (strlit("yes"), "str"),
        ],
    )
    def should_rebuild_scalar_literal(
        expr: ast.ScalarLiteral, type_: Literal["str"], create_context: ContextCreator
    ):
        ctx, g = create_context()
        actual_value = bool(expr) if isinstance(expr, ast.BoolLiteral) else expr

        _ = ctx.build_expression(expr)
        _ = ctx.build_expression(expr)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit1": ScalarLiteral(type=type_, value=actual_value),
                    "lit2": ScalarLiteral(type=type_, value=actual_value),
                },
                [],
            ),
        )

    def should_rebuild_seq_literal(create_context: ContextCreator):
        expr = ast.SeqLiteral([strlit("hello"), strlit("world")])
        ctx, g = create_context()

        _ = ctx.build_expression(expr)
        _ = ctx.build_expression(expr)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": CompositeLiteral(type="list"),
                    "e1": ScalarLiteral(type="str", value="hello"),
                    "e2": ScalarLiteral(type="str", value="world"),
                    "lit2": CompositeLiteral(type="list"),
                    "e12": ScalarLiteral(type="str", value="hello"),
                    "e22": ScalarLiteral(type="str", value="world"),
                },
                [
                    ("e1", "lit", Composition(index="0")),
                    ("e2", "lit", Composition(index="1")),
                    ("e12", "lit2", Composition(index="0")),
                    ("e22", "lit2", Composition(index="1")),
                ],
            ),
        )

    def should_rebuild_map_literal(create_context: ContextCreator):
        expr = ast.MapLiteral[ast.ScalarLiteral, ast.AnyExpression](
            [(strlit("hello"), strlit("world")), (strlit("key"), strlit("value"))]
        )
        ctx, g = create_context()

        _ = ctx.build_expression(expr)
        _ = ctx.build_expression(expr)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": CompositeLiteral(type="dict"),
                    "world": ScalarLiteral(type="str", value="world"),
                    "value": ScalarLiteral(type="str", value="value"),
                    "lit2": CompositeLiteral(type="dict"),
                    "world2": ScalarLiteral(type="str", value="world"),
                    "value2": ScalarLiteral(type="str", value="value"),
                },
                [
                    ("world", "lit", Composition(index="hello")),
                    ("value", "lit", Composition(index="key")),
                    ("world2", "lit2", Composition(index="hello")),
                    ("value2", "lit2", Composition(index="key")),
                ],
            ),
        )

    @pytest.mark.parametrize(
        "expression",
        [
            "{{ 1 + 1 }}",
            '{{ "/etc/tzinfo" | basename }}',
            '{{ lookup("indexed_items", [1,2,3]) }}',
            "{{ [1,2,3] | first }}",
            "The time is {{ now() }}",
            '{{ "/etc/tzinfo" is file }}',
            '{{ lookup("pipe", "echo Hello World") }}',
            "{{ [1,2,3] | random }}",
        ],
    )
    def should_rebuild_standalone_expression(
        expression: str, create_context: ContextCreator
    ):
        ctx, g = create_context()

        _ = ctx.build_expression(expr(expression))
        _ = ctx.build_expression(expr(expression))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e": Expression(expr=expression),
                    "iv": IntermediateValue(identifier=1),
                    "e2": Expression(expr=expression),
                    "iv2": IntermediateValue(identifier=2),
                },
                [("e", "iv", DEF), ("e2", "iv2", DEF)],
            ),
        )

    def should_rebuild_expression_with_dependencies(create_context: ContextCreator):
        ctx, g = create_context()
        ctx.define_lazy_variable(
            ident("test"), EnvironmentType.CLI_VALUES, strlit("hello world")
        )
        e = expr("Value is {{ test }}")

        _ = ctx.build_expression(e)
        _ = ctx.build_expression(e)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": ScalarLiteral(type="str", value="hello world"),
                    "var": Variable(
                        name="test",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "e": Expression(expr=e.raw),
                    "iv": IntermediateValue(identifier=1),
                    "lit2": ScalarLiteral(type="str", value="hello world"),
                    "var2": Variable(
                        name="test",
                        version=0,
                        value_version=1,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "e2": Expression(expr=e.raw),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("e", "iv", DEF),
                    ("lit", "var", DEF),
                    ("var", "e", Input()),
                    ("e2", "iv2", DEF),
                    ("lit2", "var2", DEF),
                    ("var2", "e2", Input()),
                ],
            ),
        )

    def should_build_expression_with_complex_dependencies(
        create_context: ContextCreator,
    ):
        ctx, g = create_context()
        ctx.define_lazy_variable(
            ident("test"), EnvironmentType.CLI_VALUES, expr("{{ 1 + other }}")
        )
        ctx.define_lazy_variable(ident("other"), EnvironmentType.CLI_VALUES, intlit(2))

        e = expr("Value is {{ test }}")

        _ = ctx.build_expression(e)
        _ = ctx.build_expression(e)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": ScalarLiteral(type="int", value=2),
                    "other": Variable(
                        name="other",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "test_e": Expression(expr="{{ 1 + other }}"),
                    "test_iv": IntermediateValue(identifier=1),
                    "test": Variable(
                        name="test",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "e": Expression(expr=e.raw),
                    "iv": IntermediateValue(identifier=2),
                    "lit2": ScalarLiteral(type="int", value=2),
                    "other2": Variable(
                        name="other",
                        version=0,
                        value_version=1,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "test_e2": Expression(expr="{{ 1 + other }}"),
                    "test_iv2": IntermediateValue(identifier=3),
                    "test2": Variable(
                        name="test",
                        version=0,
                        value_version=1,
                        scope_level=EnvironmentType.CLI_VALUES.value,
                    ),
                    "e2": Expression(expr=e.raw),
                    "iv2": IntermediateValue(identifier=4),
                },
                [
                    ("lit", "other", DEF),
                    ("other", "test_e", Input()),
                    ("test_e", "test_iv", DEF),
                    ("test_iv", "test", DEF),
                    ("test", "e", Input()),
                    ("e", "iv", DEF),
                    ("lit2", "other2", DEF),
                    ("other2", "test_e2", Input()),
                    ("test_e2", "test_iv2", DEF),
                    ("test_iv2", "test2", DEF),
                    ("test2", "e2", Input()),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_rebuild_seq_literal_with_expression(create_context: ContextCreator):
        seq = ast.SeqLiteral([strlit("hello"), expr("{{ 1 + 1 }}")])
        ctx, g = create_context()

        _ = ctx.build_expression(seq)
        _ = ctx.build_expression(seq)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": CompositeLiteral(type="list"),
                    "e1": ScalarLiteral(type="str", value="hello"),
                    "expr": Expression(expr="{{ 1 + 1 }}"),
                    "e2": IntermediateValue(identifier=1),
                    "lit2": CompositeLiteral(type="list"),
                    "e12": ScalarLiteral(type="str", value="hello"),
                    "expr2": Expression(expr="{{ 1 + 1 }}"),
                    "e22": IntermediateValue(identifier=2),
                },
                [
                    ("e1", "lit", Composition(index="0")),
                    ("e2", "lit", Composition(index="1")),
                    ("expr", "e2", DEF),
                    ("e12", "lit2", Composition(index="0")),
                    ("e22", "lit2", Composition(index="1")),
                    ("expr2", "e22", DEF),
                ],
            ),
        )

    def should_not_rebuild_expression_with_eager_dependencies(
        create_context: ContextCreator,
    ):
        ctx, g = create_context()
        _ = ctx.define_eager_variable(
            ident("test"), EnvironmentType.SET_FACTS_REGISTERED
        )
        e = expr("Value is {{ test }}")

        _ = ctx.build_expression(e)
        _ = ctx.build_expression(e)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "var": Variable(
                        name="test",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.SET_FACTS_REGISTERED.value,
                    ),
                    "e": Expression(expr=e.raw),
                    "iv": IntermediateValue(identifier=1),
                    "e2": Expression(expr=e.raw),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("e", "iv", DEF),
                    ("var", "e", Input()),
                    ("e2", "iv2", DEF),
                    ("var", "e2", Input()),
                ],
            ),
        )


# FIXME: These test cases are disabled pending a large rewrite of the data flow semantics, and should
# be fixed/moved later on.
def _describe_unmodified() -> None:
    @pytest.mark.parametrize(
        ("expr", "type_"),
        [("hello", "str"), ("1", "str"), ("True", "str"), ("yes", "str")],
    )
    def should_extract_literal(
        expr: str, type_: Literal["str"], create_context: ContextCreator
    ) -> None:
        ctx, g = create_context()

        _ = ctx.build_expression(strlit(expr))

        assert_graphs_match(
            g, create_graph({"lit": ScalarLiteral(type=type_, value=expr)}, [])
        )

    def should_declare_literal_variable(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("test_var"), EnvironmentType.HOST_FACTS, strlit("hello world")
        )

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": ScalarLiteral(type="str", value="hello world"),
                    "var": Variable(
                        name="test_var",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),  # UNUSED!
                },
                [("lit", "var", DEF)],
            ),
        )

    def should_extract_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        _ = ctx.build_expression(expr("hello {{ target }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "var": Variable(
                        name="target",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.UNDEFINED.value,
                    ),
                    "expr": Expression(expr="hello {{ target }}"),
                    "iv": IntermediateValue(identifier=0),
                },
                [("var", "expr", Input()), ("expr", "iv", DEF)],
            ),
        )

    def should_extract_magic_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        _ = ctx.build_expression(expr("hello {{ ansible_version }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "var": Variable(
                        name="ansible_version",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.MAGIC_VARS.value,
                    ),
                    "expr": Expression(expr="hello {{ ansible_version }}"),
                    "iv": IntermediateValue(identifier=0),
                },
                [("var", "expr", Input()), ("expr", "iv", DEF)],
            ),
        )

    def should_extract_host_facts(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        _ = ctx.build_expression(expr("hello {{ ansible_os_family }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "var": Variable(
                        name="ansible_os_family",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "expr": Expression(expr="hello {{ ansible_os_family }}"),
                    "iv": IntermediateValue(identifier=0),
                },
                [("var", "expr", Input()), ("expr", "iv", DEF)],
            ),
        )

    def should_reevaluate_template_literal(create_context: ContextCreator) -> None:
        # We don't want to deduplicate template literals yet
        ctx, g = create_context()

        _ = ctx.build_expression(strlit("hello world"))
        _ = ctx.build_expression(strlit("hello world"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit1": ScalarLiteral(type="str", value="hello world"),
                    "lit2": ScalarLiteral(type="str", value="hello world"),
                },
                [],
            ),
        )

    def should_not_reevaluate_variables(create_context: ContextCreator) -> None:
        # We don't want to deduplicate template literals yet
        ctx, g = create_context()

        _ = ctx.build_expression(expr("hello {{ target }}"))
        _ = ctx.build_expression(expr("hello {{ target }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "target": Variable(
                        name="target",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.UNDEFINED.value,
                    ),
                    "expression": Expression(expr="hello {{ target }}"),
                    "iv": IntermediateValue(identifier=1),
                },
                [("target", "expression", Input()), ("expression", "iv", DEF)],
            ),
        )

    def should_extract_variable_definition(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("msg"), EnvironmentType.HOST_FACTS, expr("hello {{ target }}")
        )
        _ = ctx.build_expression(expr("{{ msg }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "target": Variable(
                        name="target",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.UNDEFINED.value,
                    ),
                    "msg": Variable(
                        name="msg",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "e1": Expression(expr="hello {{ target }}"),
                    "e2": Expression(expr="{{ msg }}"),
                    "iv1": IntermediateValue(identifier=1),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("target", "e1", Input()),
                    ("e1", "iv1", DEF),
                    ("iv1", "msg", DEF),
                    ("msg", "e2", Input()),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    @pytest.mark.parametrize(
        ("expression", "_expected"),
        [
            ('{{ "/etc/tzinfo" | basename }}', "{{ '/etc/tzinfo' | basename }}"),
            (
                '{{ lookup("indexed_items", [1,2,3]) }}',
                "{{ lookup('indexed_items', [1, 2, 3]) }}",
            ),
            ("{{ [1,2,3] | first }}", "{{ [1, 2, 3] | first }}"),
        ],
    )
    def should_not_reevaluate_static_templates(
        expression: str, _expected: str, create_context: ContextCreator
    ) -> None:
        ctx, g = create_context()

        _ = ctx.build_expression(expr(expression))
        _ = ctx.build_expression(expr(expression))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e": Expression(expr=expression),
                    "iv": IntermediateValue(identifier=1),
                },
                [("e", "iv", DEF)],
            ),
        )


def _describe_modified() -> None:
    @pytest.mark.parametrize(
        ("expression", "_expected", "components"),
        [
            ("The time is {{ now() }}", "The time is {{ now() }}", ("function 'now'",)),
            (
                '{{ "/etc/tzinfo" is file }}',
                "{{ '/etc/tzinfo' is file }}",
                ("test 'file'",),
            ),
            (
                '{{ lookup("pipe", "echo Hello World") }}',
                "{{ lookup('pipe', 'echo Hello World') }}",
                ("lookup 'pipe'",),
            ),
            (
                "{{ [1,2,3] | random }}",
                "{{ [1, 2, 3] | random }}",
                ("filter 'random'",),
            ),
        ],
    )
    def should_reevaluate_dynamic_templates(
        expression: str,
        _expected: str,
        components: tuple[str],
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        _ = ctx.build_expression(expr(expression))
        _ = ctx.build_expression(expr(expression))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e": Expression(expr=expression, impure_components=components),
                    "iv1": IntermediateValue(identifier=1),
                    "iv2": IntermediateValue(identifier=2),
                },
                [("e", "iv1", DEF), ("e", "iv2", DEF)],
            ),
        )

    def should_reevaluate_when_variable_changed(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("a"), EnvironmentType.HOST_FACTS, strlit("hello")
        )
        _ = ctx.build_expression(expr("{{ a }} world"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(
                ident("a"), EnvironmentType.TASK_VARS, strlit("hi")
            )
            _ = ctx.build_expression(expr("{{ a }} world"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a1": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "l1": ScalarLiteral(type="str", value="hello"),
                    "e1": Expression(expr="{{ a }} world"),
                    "a2": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "l2": ScalarLiteral(type="str", value="hi"),
                    "e2": Expression(expr="{{ a }} world"),
                    "iv1": IntermediateValue(identifier=1),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("l1", "a1", DEF),
                    ("a1", "e1", Input()),
                    ("e1", "iv1", DEF),
                    ("l2", "a2", DEF),
                    ("a2", "e2", Input()),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_reevaluate_when_variable_dynamic(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("when"), EnvironmentType.HOST_FACTS, expr("{{ now() }}")
        )
        _ = ctx.build_expression(expr("The time is {{ when }}"))
        _ = ctx.build_expression(expr("The time is {{ when }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e1": Expression(
                        expr="{{ now() }}", impure_components=("function 'now'",)
                    ),
                    "iv1": IntermediateValue(identifier=1),
                    "when1": Variable(
                        name="when",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "e2": Expression(expr="The time is {{ when }}"),
                    "iv2": IntermediateValue(identifier=2),
                    "e3": Expression(expr="The time is {{ when }}"),
                    "iv3": IntermediateValue(identifier=3),
                    "when2": Variable(
                        name="when",
                        version=0,
                        value_version=1,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "iv4": IntermediateValue(identifier=4),
                },
                [
                    ("e1", "iv1", DEF),
                    ("iv1", "when1", DEF),
                    ("when1", "e2", Input()),
                    ("e2", "iv2", DEF),
                    ("e1", "iv3", DEF),
                    ("iv3", "when2", DEF),
                    ("when2", "e3", Input()),
                    ("e3", "iv4", DEF),
                ],
            ),
        )

    def should_reevaluate_with_deeply_nested_expressions(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("a"), EnvironmentType.HOST_FACTS, strlit("hello")
        )
        ctx.define_lazy_variable(
            ident("b"), EnvironmentType.HOST_FACTS, expr("{{ a }} world")
        )
        _ = ctx.build_expression(expr("{{ b }}!"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(
                ident("a"), EnvironmentType.TASK_VARS, strlit("hi")
            )
            _ = ctx.build_expression(expr("{{ b }}!"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a1": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "l1": ScalarLiteral(type="str", value="hello"),
                    "b1": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "e1": Expression(expr="{{ a }} world"),
                    "i1": IntermediateValue(identifier=1),
                    "e2": Expression(expr="{{ b }}!"),
                    "i2": IntermediateValue(identifier=2),
                    "a2": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "l2": ScalarLiteral(type="str", value="hi"),
                    "b2": Variable(
                        name="b",
                        version=0,
                        value_version=1,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "e3": Expression(expr="{{ a }} world"),
                    "i3": IntermediateValue(identifier=3),
                    "e4": Expression(expr="{{ b }}!"),
                    "i4": IntermediateValue(identifier=4),
                },
                [
                    ("l1", "a1", DEF),
                    ("a1", "e1", Input()),
                    ("e1", "i1", DEF),
                    ("i1", "b1", DEF),
                    ("b1", "e2", Input()),
                    ("e2", "i2", DEF),
                    ("l2", "a2", DEF),
                    ("a2", "e3", Input()),
                    ("e3", "i3", DEF),
                    ("i3", "b2", DEF),
                    ("b2", "e4", Input()),
                    ("e4", "i4", DEF),
                ],
            ),
        )

    def should_reevaluate_only_one_var(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("a"), EnvironmentType.HOST_FACTS, strlit("hello")
        )
        ctx.define_lazy_variable(
            ident("b"), EnvironmentType.HOST_FACTS, strlit("world")
        )
        _ = ctx.build_expression(expr("{{ a }} {{ b }}!"))
        ctx.define_lazy_variable(ident("a"), EnvironmentType.INCLUDE_VARS, strlit("hi"))
        _ = ctx.build_expression(expr("{{ a }} {{ b }}!"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a1": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "l1": ScalarLiteral(type="str", value="hello"),
                    "b": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "l2": ScalarLiteral(type="str", value="world"),
                    "e1": Expression(expr="{{ a }} {{ b }}!"),
                    "i1": IntermediateValue(identifier=1),
                    "a2": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.INCLUDE_VARS.value,
                    ),
                    "l3": ScalarLiteral(type="str", value="hi"),
                    "e2": Expression(expr="{{ a }} {{ b }}!"),
                    "i2": IntermediateValue(identifier=2),
                },
                [
                    ("l1", "a1", DEF),
                    ("l2", "b", DEF),
                    ("a1", "e1", Input()),
                    ("b", "e1", Input()),
                    ("e1", "i1", DEF),
                    ("l3", "a2", DEF),
                    ("a2", "e2", Input()),
                    ("b", "e2", Input()),
                    ("e2", "i2", DEF),
                ],
            ),
        )


def _describe_scoping() -> None:
    def should_use_most_specific_scope(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(ident("a"), EnvironmentType.HOST_FACTS, strlit("1"))
        _ = ctx.build_expression(expr("1 {{ a }}"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("a"), EnvironmentType.TASK_VARS, strlit("2"))
            _ = ctx.build_expression(expr("2 {{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "1": ScalarLiteral(type="str", value="1"),
                    "e1": Expression(expr="1 {{ a }}"),
                    "iv1": IntermediateValue(identifier=1),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "2": ScalarLiteral(type="str", value="2"),
                    "e2": Expression(expr="2 {{ a }}"),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("1", "aouter", DEF),
                    ("aouter", "e1", Input()),
                    ("e1", "iv1", DEF),
                    ("2", "ainner", DEF),
                    ("ainner", "e2", Input()),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_override_root_scope_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(ident("a"), EnvironmentType.HOST_FACTS, strlit("1"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(
                ident("a"), EnvironmentType.SET_FACTS_REGISTERED, strlit("2")
            )
        _ = ctx.build_expression(expr("{{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": ScalarLiteral(type="str", value="1"),
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),  # UNUSED!
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.SET_FACTS_REGISTERED.value,
                    ),
                    "2": ScalarLiteral(type="str", value="2"),
                    "e": Expression(expr="{{ a }}"),
                    "iv": IntermediateValue(identifier=1),
                },
                [
                    ("1", "aouter", DEF),
                    ("2", "ainner", DEF),
                    ("ainner", "e", Input()),
                    ("e", "iv", DEF),
                ],
            ),
        )

    def should_never_override_magic_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            ctx.define_lazy_variable(
                ident("ansible_version"), EnvironmentType.INCLUDE_PARAMS, strlit("123")
            )
            _ = ctx.build_expression(expr("{{ ansible_version }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral(type="str", value="123"),
                    "unused": Variable(
                        name="ansible_version",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.INCLUDE_PARAMS.value,
                    ),  # UNUSED!
                    "actual": Variable(
                        name="ansible_version",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.MAGIC_VARS.value,
                    ),
                    "e": Expression(expr="{{ ansible_version }}"),
                    "iv": IntermediateValue(identifier=1),
                },
                [("l123", "unused", DEF), ("actual", "e", Input()), ("e", "iv", DEF)],
            ),
        )

    def should_use_same_magic_variable(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            ctx.define_lazy_variable(
                ident("ansible_version"), EnvironmentType.INCLUDE_PARAMS, strlit("123")
            )
            _ = ctx.build_expression(expr("1: {{ ansible_version }}"))
            _ = ctx.build_expression(expr("2: {{ ansible_version }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral(type="str", value="123"),
                    "unused": Variable(
                        name="ansible_version",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.INCLUDE_PARAMS.value,
                    ),  # UNUSED!
                    "actual": Variable(
                        name="ansible_version",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.MAGIC_VARS.value,
                    ),
                    "e1": Expression(expr="1: {{ ansible_version }}"),
                    "e2": Expression(expr="2: {{ ansible_version }}"),
                    "iv1": IntermediateValue(identifier=1),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("l123", "unused", DEF),
                    ("actual", "e1", Input()),
                    ("actual", "e2", Input()),
                    ("e1", "iv1", DEF),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_override_host_facts_at_higher_prec(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            ctx.define_lazy_variable(
                ident("ansible_os_family"),
                EnvironmentType.INCLUDE_PARAMS,
                strlit("123"),
            )
            _ = ctx.build_expression(expr("{{ ansible_os_family }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral(type="str", value="123"),
                    "actual": Variable(
                        name="ansible_os_family",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.INCLUDE_PARAMS.value,
                    ),
                    "e": Expression(expr="{{ ansible_os_family }}"),
                    "iv": IntermediateValue(identifier=1),
                },
                [("l123", "actual", DEF), ("actual", "e", Input()), ("e", "iv", DEF)],
            ),
        )

    def should_not_override_host_facts_at_lower_prec(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.ROLE_DEFAULTS):
            ctx.define_lazy_variable(
                ident("ansible_os_family"), EnvironmentType.ROLE_DEFAULTS, strlit("123")
            )
            _ = ctx.build_expression(expr("{{ ansible_os_family }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral(type="str", value="123"),
                    "unused": Variable(
                        name="ansible_os_family",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.ROLE_DEFAULTS.value,
                    ),
                    "actual": Variable(
                        name="ansible_os_family",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "e": Expression(expr="{{ ansible_os_family }}"),
                    "iv": IntermediateValue(identifier=1),
                },
                [("l123", "unused", DEF), ("actual", "e", Input()), ("e", "iv", DEF)],
            ),
        )

    def should_override_host_facts_combo_precedence(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.ROLE_DEFAULTS):
            ctx.define_lazy_variable(
                ident("ansible_os_family"), EnvironmentType.ROLE_DEFAULTS, strlit("123")
            )
            _ = ctx.build_expression(expr("{{ ansible_os_family }}"))
            with ctx.enter_scope(EnvironmentType.ROLE_VARS):
                ctx.define_lazy_variable(
                    ident("ansible_os_family"), EnvironmentType.ROLE_VARS, strlit("456")
                )
                _ = ctx.build_expression(expr("{{ ansible_os_family }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral(type="str", value="123"),
                    "l456": ScalarLiteral(type="str", value="456"),
                    "unused": Variable(
                        name="ansible_os_family",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.ROLE_DEFAULTS.value,
                    ),
                    "actual_host_fact": Variable(
                        name="ansible_os_family",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "actual_role_var": Variable(
                        name="ansible_os_family",
                        version=2,
                        value_version=0,
                        scope_level=EnvironmentType.ROLE_VARS.value,
                    ),
                    "e_host_fact": Expression(expr="{{ ansible_os_family }}"),
                    "e_role_var": Expression(expr="{{ ansible_os_family }}"),
                    "iv_host_fact": IntermediateValue(identifier=1),
                    "iv_role_var": IntermediateValue(identifier=2),
                },
                [
                    ("l123", "unused", DEF),
                    ("l456", "actual_role_var", DEF),
                    ("actual_host_fact", "e_host_fact", Input()),
                    ("e_host_fact", "iv_host_fact", DEF),
                    ("actual_role_var", "e_role_var", Input()),
                    ("e_role_var", "iv_role_var", DEF),
                ],
            ),
        )

    def should_use_same_host_fact(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        _ = ctx.build_expression(expr("1: {{ ansible_os_family }}"))
        _ = ctx.build_expression(expr("2: {{ ansible_os_family }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "actual": Variable(
                        name="ansible_os_family",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "e1": Expression(expr="1: {{ ansible_os_family }}"),
                    "e2": Expression(expr="2: {{ ansible_os_family }}"),
                    "iv1": IntermediateValue(identifier=1),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("actual", "e1", Input()),
                    ("actual", "e2", Input()),
                    ("e1", "iv1", DEF),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_reuse_prev_outer_template_in_inner(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(ident("a"), EnvironmentType.HOST_FACTS, strlit("1"))
        _ = ctx.build_expression(expr("1 {{ a }}"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            _ = ctx.build_expression(expr("1 {{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "1": ScalarLiteral(type="str", value="1"),
                    "e1": Expression(expr="1 {{ a }}"),
                    "iv1": IntermediateValue(identifier=1),
                },
                [("1", "aouter", DEF), ("aouter", "e1", Input()), ("e1", "iv1", DEF)],
            ),
        )

    def should_reuse_prev_outer_template_in_outer(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(ident("a"), EnvironmentType.HOST_FACTS, strlit("1"))
        _ = ctx.build_expression(expr("1 {{ a }}"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("a"), EnvironmentType.TASK_VARS, strlit("2"))
        _ = ctx.build_expression(expr("1 {{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),  # UNUSED!
                    "1": ScalarLiteral(type="str", value="1"),
                    "2": ScalarLiteral(type="str", value="2"),
                    "e1": Expression(expr="1 {{ a }}"),
                    "iv1": IntermediateValue(identifier=1),
                },
                [
                    ("1", "aouter", DEF),
                    ("2", "ainner", DEF),
                    ("aouter", "e1", Input()),
                    ("e1", "iv1", DEF),
                ],
            ),
        )

    def should_hoist_template(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(ident("a"), EnvironmentType.HOST_FACTS, strlit("1"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("c"), EnvironmentType.TASK_VARS, strlit("c"))
            _ = ctx.build_expression(expr("1 {{ a }}"))
            ctx.define_lazy_variable(ident("a"), EnvironmentType.TASK_VARS, strlit("2"))
        _ = ctx.build_expression(expr("1 {{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "c": Variable(
                        name="c",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "1": ScalarLiteral(type="str", value="1"),
                    "clit": ScalarLiteral(type="str", value="c"),
                    "2": ScalarLiteral(type="str", value="2"),
                    "e1": Expression(expr="1 {{ a }}"),
                    "iv1": IntermediateValue(identifier=1),
                },
                [
                    ("1", "aouter", DEF),
                    ("2", "ainner", DEF),
                    ("clit", "c", DEF),
                    ("aouter", "e1", Input()),
                    ("e1", "iv1", DEF),
                ],
            ),
        )

    def should_not_hoist_template_if_overridden(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        # Difference to 'should_use_most_specific_scope': Same template here,
        # different template there
        ctx.define_lazy_variable(ident("a"), EnvironmentType.HOST_FACTS, strlit("1"))
        _ = ctx.build_expression(expr("1 {{ a }}"))
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("a"), EnvironmentType.TASK_VARS, strlit("2"))
            _ = ctx.build_expression(expr("1 {{ a }}"))
        _ = ctx.build_expression(expr("1 {{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "1": ScalarLiteral(type="str", value="1"),
                    "e1": Expression(expr="1 {{ a }}"),
                    "iv1": IntermediateValue(identifier=1),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "2": ScalarLiteral(type="str", value="2"),
                    "e2": Expression(expr="1 {{ a }}"),
                    "iv2": IntermediateValue(identifier=2),
                },
                [
                    ("1", "aouter", DEF),
                    ("aouter", "e1", Input()),
                    ("e1", "iv1", DEF),
                    ("2", "ainner", DEF),
                    ("ainner", "e2", Input()),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_evaluate_var_into_template_scope(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("a"), EnvironmentType.HOST_FACTS, expr("{{ b }}")
        )
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("b"), EnvironmentType.TASK_VARS, strlit("1"))
            _ = ctx.build_expression(expr("{{ a }}"))
        ctx.define_lazy_variable(ident("b"), EnvironmentType.HOST_FACTS, strlit("2"))
        _ = ctx.build_expression(expr("{{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "ai": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "aei": Expression(expr="{{ b }}"),
                    "aeiv": IntermediateValue(identifier=0),
                    "binner": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "bil": ScalarLiteral(type="str", value="1"),
                    "ei": Expression(expr="{{ a }}"),
                    "eiv": IntermediateValue(identifier=1),
                    "bouter": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "bol": ScalarLiteral(type="str", value="2"),
                    "eo": Expression(expr="{{ a }}"),
                    "eov": IntermediateValue(identifier=2),
                    "ao": Variable(
                        name="a",
                        version=0,
                        value_version=1,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "aeo": Expression(expr="{{ b }}"),
                    "aeov": IntermediateValue(identifier=2),
                },
                [
                    ("aei", "aeiv", DEF),
                    ("aeiv", "ai", DEF),
                    ("bil", "binner", DEF),
                    ("ei", "eiv", DEF),
                    ("ai", "ei", Input()),
                    ("binner", "aei", Input()),
                    ("eo", "eov", DEF),
                    ("ao", "eo", Input()),
                    ("aeo", "aeov", DEF),
                    ("aeov", "ao", DEF),
                    ("bouter", "aeo", Input()),
                    ("bol", "bouter", DEF),
                ],
            ),
        )

    def should_reuse_nested_templates(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(
                ident("a"), EnvironmentType.TASK_VARS, expr("{{ 'hello' | reverse }}")
            )
            ctx.define_lazy_variable(
                ident("b"), EnvironmentType.TASK_VARS, expr("{{ c | reverse }}")
            )
            ctx.define_lazy_variable(
                ident("c"), EnvironmentType.TASK_VARS, strlit("world")
            )
            _ = ctx.build_expression(expr("{{ b }} {{ a }}"))
        ctx.define_lazy_variable(
            ident("a"), EnvironmentType.HOST_FACTS, expr("{{ 'hello' | reverse }}")
        )
        _ = ctx.build_expression(expr("{{ b }} {{ a }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "c": Variable(
                        name="c",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "cl": ScalarLiteral(type="str", value="world"),
                    "bie": Expression(expr="{{ c | reverse }}"),
                    "biv": IntermediateValue(identifier=0),
                    "binner": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "ae": Expression(expr="{{ 'hello' | reverse }}"),
                    "aiv": IntermediateValue(identifier=1),
                    "ai": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "ie": Expression(expr="{{ b }} {{ a }}"),
                    "iev": IntermediateValue(identifier=2),
                    "bouter": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.UNDEFINED.value,
                    ),
                    "ao": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "oe": Expression(expr="{{ b }} {{ a }}"),
                    "oev": IntermediateValue(identifier=3),
                },
                [
                    ("cl", "c", DEF),
                    ("c", "bie", Input()),
                    ("bie", "biv", DEF),
                    ("biv", "binner", DEF),
                    ("ae", "aiv", DEF),
                    ("aiv", "ai", DEF),
                    ("binner", "ie", Input()),
                    ("ai", "ie", Input()),
                    ("ie", "iev", DEF),
                    ("aiv", "ao", DEF),
                    ("bouter", "oe", Input()),
                    ("ao", "oe", Input()),
                    ("oe", "oev", DEF),
                ],
            ),
        )

    def should_hoist_variable_binding(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_lazy_variable(
            ident("a"), EnvironmentType.HOST_FACTS, expr("{{ b }}")
        )
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("b"), EnvironmentType.TASK_VARS, strlit("1"))
            with ctx.enter_scope(EnvironmentType.TASK_VARS):
                _ = ctx.build_expression(expr("{{ a }}"))
            _ = ctx.build_expression(expr("{{ a }}"))  # Should reuse above expr

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "b": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "lb": ScalarLiteral(type="str", value="1"),
                    "ae": Expression(expr="{{ b }}"),
                    "aei": IntermediateValue(identifier=0),
                    "te": Expression(expr="{{ a }}"),
                    "tei": IntermediateValue(identifier=1),
                },
                [
                    ("lb", "b", DEF),
                    ("aei", "a", DEF),
                    ("ae", "aei", DEF),
                    ("b", "ae", Input()),
                    ("a", "te", Input()),
                    ("te", "tei", DEF),
                ],
            ),
        )

    def should_respect_precedence(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ln = ScalarLiteral(type="int", value=1)
        g.add_node(ln)
        vn = ctx.define_eager_variable("b", EnvironmentType.SET_FACTS_REGISTERED)
        g.add_edge(ln, vn, DEF)

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("b"), EnvironmentType.TASK_VARS, strlit("2"))
            _ = ctx.build_expression(expr("{{ b }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": ScalarLiteral(type="int", value=1),
                    "2": ScalarLiteral(type="str", value="2"),
                    "bsf": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.SET_FACTS_REGISTERED.value,
                    ),
                    "bt": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "be": Expression(expr="{{ b }}"),
                    "beiv": IntermediateValue(identifier=0),
                },
                {
                    ("1", "bsf", DEF),
                    ("2", "bt", DEF),
                    ("bsf", "be", Input()),
                    ("be", "beiv", DEF),
                },
            ),
        )

    def should_respect_precedence_register_element(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("b"), EnvironmentType.TASK_VARS, strlit("1"))
        ln = ScalarLiteral(type="int", value=2)
        g.add_node(ln)
        vn = ctx.define_eager_variable("b", EnvironmentType.SET_FACTS_REGISTERED)
        g.add_edge(ln, vn, DEF)

        _ = ctx.build_expression(expr("{{ b }}"))

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": ScalarLiteral(type="str", value="1"),
                    "2": ScalarLiteral(type="int", value=2),
                    "binner": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "b": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.SET_FACTS_REGISTERED.value,
                    ),
                    "be": Expression(expr="{{ b }}"),
                    "beiv": IntermediateValue(identifier=0),
                },
                {
                    ("1", "binner", DEF),
                    ("2", "b", DEF),
                    ("b", "be", Input()),
                    ("be", "beiv", DEF),
                },
            ),
        )

    def should_respect_precedence_overriding_in_template(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_lazy_variable(ident("b"), EnvironmentType.TASK_VARS, strlit("1"))
            ln = ScalarLiteral(type="int", value=2)
            g.add_node(ln)
            vn = ctx.define_eager_variable("b", EnvironmentType.SET_FACTS_REGISTERED)
            g.add_edge(ln, vn, DEF)
            _ = ctx.build_expression(expr("{{ b }}"))
        _ = ctx.build_expression(expr("{{ b }}"))  # Should reuse above expr

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": ScalarLiteral(type="str", value="1"),
                    "2": ScalarLiteral(type="int", value=2),
                    "b1": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.TASK_VARS.value,
                    ),
                    "b": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=EnvironmentType.SET_FACTS_REGISTERED.value,
                    ),
                    "be": Expression(expr="{{ b }}"),
                    "beiv": IntermediateValue(identifier=0),
                },
                {
                    ("1", "b1", DEF),
                    ("2", "b", DEF),
                    ("b", "be", Input()),
                    ("be", "beiv", DEF),
                },
            ),
        )
