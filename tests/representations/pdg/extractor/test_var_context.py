# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import Callable

from pathlib import Path

import pytest
from pytest_mock import MockerFixture

from scansible.representations.pdg import (
    DEF,
    USE,
    Expression,
    Graph,
    IntermediateValue,
    ScalarLiteral,
    Variable,
)
from scansible.representations.pdg.extractor.context import ExtractionContext
from scansible.representations.pdg.extractor.expressions import (
    EnvironmentType,
    VarContext,
)
from test_utils.graph_matchers import assert_graphs_match, create_graph

ContextCreator = Callable[[], tuple[VarContext, Graph]]


@pytest.fixture()
def create_context(g: Graph, mocker: MockerFixture) -> ContextCreator:
    return lambda: (
        ExtractionContext(
            g,
            mocker.Mock(
                **{
                    "path": Path("/test"),
                    "root.main_tasks_file.file_path": Path("tasks/main.yml"),
                }
            ),
            mocker.Mock(),
            lenient=True,
        ).vars,
        g,
    )


def describe_unmodified() -> None:
    @pytest.mark.parametrize(
        "expr, type", [("hello", "str"), ("1", "str"), ("True", "str"), ("yes", "str")]
    )
    def should_extract_literal(
        expr: str, type: str, create_context: ContextCreator
    ) -> None:
        ctx, g = create_context()

        ctx.build_expression(expr)

        assert_graphs_match(
            g, create_graph({"lit": ScalarLiteral(type="str", value=expr)}, [])
        )

    def should_declare_literal_variable(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable(
            "test_var", EnvironmentType.HOST_FACTS, "hello world"
        )

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": ScalarLiteral(type="str", value="hello world"),
                    "var": Variable(
                        "test_var", 0, 0, EnvironmentType.HOST_FACTS.value
                    ),  # UNUSED!
                },
                [("lit", "var", DEF)],
            ),
        )

    def should_extract_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.build_expression("hello {{ target }}")

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
                [
                    ("var", "expr", USE),
                    ("expr", "iv", DEF),
                ],
            ),
        )

    def should_extract_magic_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.build_expression("hello {{ ansible_version }}")

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
                [
                    ("var", "expr", USE),
                    ("expr", "iv", DEF),
                ],
            ),
        )

    def should_extract_host_facts(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.build_expression("hello {{ ansible_os_family }}")

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
                [
                    ("var", "expr", USE),
                    ("expr", "iv", DEF),
                ],
            ),
        )

    def should_reevaluate_template_literal(create_context: ContextCreator) -> None:
        # We don't want to deduplicate template literals yet
        ctx, g = create_context()

        ctx.build_expression("hello world")
        ctx.build_expression("hello world")

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

        ctx.build_expression("hello {{ target }}")
        ctx.build_expression("hello {{ target }}")

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
                [("target", "expression", USE), ("expression", "iv", DEF)],
            ),
        )

    def should_extract_variable_definition(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable(
            "msg", EnvironmentType.HOST_FACTS, "hello {{ target }}"
        )
        ctx.build_expression("{{ msg }}")

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
                    ("target", "e1", USE),
                    ("e1", "iv1", DEF),
                    ("iv1", "msg", DEF),
                    ("msg", "e2", USE),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    @pytest.mark.parametrize(
        "expr",
        [
            '{{ "/etc/tzinfo" | basename }}',
            '{{ lookup("indexed_items", [1,2,3]) }}',
            "{{ [1,2,3] | first }}",
        ],
    )
    def should_not_reevaluate_static_templates(
        expr: str, create_context: ContextCreator
    ) -> None:
        ctx, g = create_context()

        ctx.build_expression(expr)
        ctx.build_expression(expr)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e": Expression(expr=expr),
                    "iv": IntermediateValue(identifier=1),
                },
                [("e", "iv", DEF)],
            ),
        )


def describe_modified() -> None:
    @pytest.mark.parametrize(
        "expr, components",
        [
            ("The time is {{ now() }}", ("function 'now'",)),
            ('{{ "/etc/tzinfo" is file }}', ("test 'file'",)),
            ('{{ lookup("pipe", "echo Hello World") }}', ("lookup 'pipe'",)),
            ("{{ [1,2,3] | random }}", ("filter 'random'",)),
        ],
    )
    def should_reevaluate_dynamic_templates(
        expr: str, components: tuple[str], create_context: ContextCreator
    ) -> None:
        ctx, g = create_context()

        ctx.build_expression(expr)
        ctx.build_expression(expr)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e": Expression(expr=expr, impure_components=components),
                    "iv1": IntermediateValue(identifier=1),
                    "iv2": IntermediateValue(identifier=2),
                },
                [("e", "iv1", DEF), ("e", "iv2", DEF)],
            ),
        )

    def should_reevaluate_when_variable_changed(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "hello")
        ctx.build_expression("{{ a }} world")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("a", EnvironmentType.TASK_VARS, "hi")
            ctx.build_expression("{{ a }} world")

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
                    ("a1", "e1", USE),
                    ("e1", "iv1", DEF),
                    ("l2", "a2", DEF),
                    ("a2", "e2", USE),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_reevaluate_when_variable_dynamic(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable(
            "when", EnvironmentType.HOST_FACTS, "{{ now() }}"
        )
        ctx.build_expression("The time is {{ when }}")
        ctx.build_expression("The time is {{ when }}")

        e2 = Expression(expr="The time is {{ when }}")
        e3 = Expression(expr="The time is {{ when }}")
        # Specify node ID to ensure proper match with duplicates
        e2.node_id = 100
        e3.node_id = 101

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e1": Expression(
                        expr="{{ now() }}",
                        impure_components=("function 'now'",),
                    ),
                    "iv1": IntermediateValue(identifier=1),
                    "when1": Variable(
                        name="when",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "e2": e2,
                    "iv2": IntermediateValue(identifier=2),
                    "e3": e3,
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
                    ("when1", "e2", USE),
                    ("e2", "iv2", DEF),
                    ("e1", "iv3", DEF),
                    ("iv3", "when2", DEF),
                    ("when2", "e3", USE),
                    ("e3", "iv4", DEF),
                ],
            ),
        )

    def should_reevaluate_with_deeply_nested_expressions(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "hello")
        ctx.define_initialised_variable(
            "b", EnvironmentType.HOST_FACTS, "{{ a }} world"
        )
        ctx.build_expression("{{ b }}!")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("a", EnvironmentType.TASK_VARS, "hi")
            ctx.build_expression("{{ b }}!")

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
                    ("a1", "e1", USE),
                    ("e1", "i1", DEF),
                    ("i1", "b1", DEF),
                    ("b1", "e2", USE),
                    ("e2", "i2", DEF),
                    ("l2", "a2", DEF),
                    ("a2", "e3", USE),
                    ("e3", "i3", DEF),
                    ("i3", "b2", DEF),
                    ("b2", "e4", USE),
                    ("e4", "i4", DEF),
                ],
            ),
        )

    def should_reevaluate_only_one_var(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "hello")
        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "world")
        ctx.build_expression("{{ a }} {{ b }}!")
        ctx.define_initialised_variable("a", EnvironmentType.INCLUDE_VARS, "hi")
        ctx.build_expression("{{ a }} {{ b }}!")

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
                    ("a1", "e1", USE),
                    ("b", "e1", USE),
                    ("e1", "i1", DEF),
                    ("l3", "a2", DEF),
                    ("a2", "e2", USE),
                    ("b", "e2", USE),
                    ("e2", "i2", DEF),
                ],
            ),
        )


def describe_scoping() -> None:
    def should_use_most_specific_scope(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "1")
        ctx.build_expression("1 {{ a }}")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("a", EnvironmentType.TASK_VARS, "2")
            ctx.build_expression("2 {{ a }}")

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
                    ("aouter", "e1", USE),
                    ("e1", "iv1", DEF),
                    ("2", "ainner", DEF),
                    ("ainner", "e2", USE),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_override_root_scope_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "1")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable(
                "a", EnvironmentType.SET_FACTS_REGISTERED, "2"
            )
        ctx.build_expression("{{ a }}")

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
                    ("ainner", "e", USE),
                    ("e", "iv", DEF),
                ],
            ),
        )

    def should_never_override_magic_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            ctx.define_initialised_variable(
                "ansible_version", EnvironmentType.INCLUDE_PARAMS, "123"
            )
            ctx.build_expression("{{ ansible_version }}")

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral("str", "123"),
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
                [
                    ("l123", "unused", DEF),
                    ("actual", "e", USE),
                    ("e", "iv", DEF),
                ],
            ),
        )

    def should_use_same_magic_variable(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.INCLUDE_PARAMS):
            ctx.define_initialised_variable(
                "ansible_version", EnvironmentType.INCLUDE_PARAMS, "123"
            )
            ctx.build_expression("1: {{ ansible_version }}")
            ctx.build_expression("2: {{ ansible_version }}")

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral("str", "123"),
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
                    ("actual", "e1", USE),
                    ("actual", "e2", USE),
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
            ctx.define_initialised_variable(
                "ansible_os_family", EnvironmentType.INCLUDE_PARAMS, "123"
            )
            ctx.build_expression("{{ ansible_os_family }}")

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral("str", "123"),
                    "actual": Variable(
                        name="ansible_os_family",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.INCLUDE_PARAMS.value,
                    ),
                    "e": Expression(expr="{{ ansible_os_family }}"),
                    "iv": IntermediateValue(identifier=1),
                },
                [
                    ("l123", "actual", DEF),
                    ("actual", "e", USE),
                    ("e", "iv", DEF),
                ],
            ),
        )

    def should_not_override_host_facts_at_lower_prec(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.ROLE_DEFAULTS):
            ctx.define_initialised_variable(
                "ansible_os_family", EnvironmentType.ROLE_DEFAULTS, "123"
            )
            ctx.build_expression("{{ ansible_os_family }}")

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral("str", "123"),
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
                [
                    ("l123", "unused", DEF),
                    ("actual", "e", USE),
                    ("e", "iv", DEF),
                ],
            ),
        )

    def should_override_host_facts_combo_precedence(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.ROLE_DEFAULTS):
            ctx.define_initialised_variable(
                "ansible_os_family", EnvironmentType.ROLE_DEFAULTS, "123"
            )
            ctx.build_expression("{{ ansible_os_family }}")
            with ctx.enter_scope(EnvironmentType.ROLE_VARS):
                ctx.define_initialised_variable(
                    "ansible_os_family", EnvironmentType.ROLE_VARS, "456"
                )
                ctx.build_expression("{{ ansible_os_family }}")

        assert_graphs_match(
            g,
            create_graph(
                {
                    "l123": ScalarLiteral("str", "123"),
                    "l456": ScalarLiteral("str", "456"),
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
                    ("actual_host_fact", "e_host_fact", USE),
                    ("e_host_fact", "iv_host_fact", DEF),
                    ("actual_role_var", "e_role_var", USE),
                    ("e_role_var", "iv_role_var", DEF),
                ],
            ),
        )

    def should_use_same_host_fact(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.build_expression("1: {{ ansible_os_family }}")
        ctx.build_expression("2: {{ ansible_os_family }}")

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
                    ("actual", "e1", USE),
                    ("actual", "e2", USE),
                    ("e1", "iv1", DEF),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_reuse_prev_outer_template_in_inner(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "1")
        ctx.build_expression("1 {{ a }}")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.build_expression("1 {{ a }}")

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
                [
                    ("1", "aouter", DEF),
                    ("aouter", "e1", USE),
                    ("e1", "iv1", DEF),
                ],
            ),
        )

    def should_reuse_prev_outer_template_in_outer(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "1")
        ctx.build_expression("1 {{ a }}")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("a", EnvironmentType.TASK_VARS, "2")
        ctx.build_expression("1 {{ a }}")

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
                    ("aouter", "e1", USE),
                    ("e1", "iv1", DEF),
                ],
            ),
        )

    def should_hoist_template(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "1")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("c", EnvironmentType.TASK_VARS, "c")
            ctx.build_expression("1 {{ a }}")
            ctx.define_initialised_variable("a", EnvironmentType.TASK_VARS, "2")
        ctx.build_expression("1 {{ a }}")

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
                    ("aouter", "e1", USE),
                    ("e1", "iv1", DEF),
                ],
            ),
        )

    def should_not_hoist_template_if_overridden(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        # Difference to 'should_use_most_specific_scope': Same template here,
        # different template there
        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "1")
        ctx.build_expression("1 {{ a }}")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("a", EnvironmentType.TASK_VARS, "2")
            ctx.build_expression("1 {{ a }}")
        ctx.build_expression("1 {{ a }}")

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
                    ("aouter", "e1", USE),
                    ("e1", "iv1", DEF),
                    ("2", "ainner", DEF),
                    ("ainner", "e2", USE),
                    ("e2", "iv2", DEF),
                ],
            ),
        )

    def should_evaluate_var_into_template_scope(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "{{ b }}")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("b", EnvironmentType.TASK_VARS, "1")
            ctx.build_expression("{{ a }}")
        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "2")
        ctx.build_expression("{{ a }}")

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
                    ("ai", "ei", USE),
                    ("binner", "aei", USE),
                    ("eo", "eov", DEF),
                    ("ao", "eo", USE),
                    ("aeo", "aeov", DEF),
                    ("aeov", "ao", DEF),
                    ("bouter", "aeo", USE),
                    ("bol", "bouter", DEF),
                ],
            ),
        )

    def should_reuse_nested_templates(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable(
                "a", EnvironmentType.TASK_VARS, "{{ 'hello' | reverse }}"
            )
            ctx.define_initialised_variable(
                "b", EnvironmentType.TASK_VARS, "{{ c | reverse }}"
            )
            ctx.define_initialised_variable("c", EnvironmentType.TASK_VARS, "world")
            ctx.build_expression("{{ b }} {{ a }}")
        ctx.define_initialised_variable(
            "a", EnvironmentType.HOST_FACTS, "{{ 'hello' | reverse }}"
        )
        ctx.build_expression("{{ b }} {{ a }}")

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
                    ("c", "bie", USE),
                    ("bie", "biv", DEF),
                    ("biv", "binner", DEF),
                    ("ae", "aiv", DEF),
                    ("aiv", "ai", DEF),
                    ("binner", "ie", USE),
                    ("ai", "ie", USE),
                    ("ie", "iev", DEF),
                    ("aiv", "ao", DEF),
                    ("bouter", "oe", USE),
                    ("ao", "oe", USE),
                    ("oe", "oev", DEF),
                ],
            ),
        )

    def should_hoist_variable_binding(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "{{ b }}")
        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("b", EnvironmentType.TASK_VARS, "1")
            with ctx.enter_scope(EnvironmentType.TASK_VARS):
                ctx.build_expression("{{ a }}")
            ctx.build_expression("{{ a }}")  # Should reuse above expr

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
                    ("b", "ae", USE),
                    ("a", "te", USE),
                    ("te", "tei", DEF),
                ],
            ),
        )

    def should_respect_precedence(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ln = ScalarLiteral(type="int", value=1)
        g.add_node(ln)
        _ = ctx.define_fact("b", EnvironmentType.SET_FACTS_REGISTERED, 1, ln)

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("b", EnvironmentType.TASK_VARS, "2")
            ctx.build_expression("{{ b }}")

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
                    ("bsf", "be", USE),
                    ("be", "beiv", DEF),
                },
            ),
        )

    def should_respect_precedence_register_element(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("b", EnvironmentType.TASK_VARS, "1")
        ln = ScalarLiteral(type="int", value=2)
        g.add_node(ln)
        _ = ctx.define_fact("b", EnvironmentType.SET_FACTS_REGISTERED, 2, ln)
        ctx.build_expression("{{ b }}")

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
                    ("b", "be", USE),
                    ("be", "beiv", DEF),
                },
            ),
        )

    def should_respect_precedence_overriding_in_template(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        with ctx.enter_scope(EnvironmentType.TASK_VARS):
            ctx.define_initialised_variable("b", EnvironmentType.TASK_VARS, "1")
            ln = ScalarLiteral(type="int", value=2)
            g.add_node(ln)
            _ = ctx.define_fact("b", EnvironmentType.SET_FACTS_REGISTERED, 2, ln)
            ctx.build_expression("{{ b }}")
        ctx.build_expression("{{ b }}")  # Should reuse above expr

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
                    ("b", "be", USE),
                    ("be", "beiv", DEF),
                },
            ),
        )


# Caching was disabled.
def _describe_caching() -> None:
    def should_cache_dynamic_template_variables(create_context: ContextCreator) -> None:
        ctx, _ = create_context()

        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "{{ now() }}")
        with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
            d1 = ctx.build_expression("{{ b }}")
            d2 = ctx.build_expression("{{ b }}")  # Should reuse above

        assert d1 is d2

    def should_discard_after_leaving_scope(create_context: ContextCreator) -> None:
        ctx, _ = create_context()

        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "{{ now() }}")
        with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
            d1 = ctx.build_expression("{{ b }}")
            d2 = ctx.build_expression("{{ b }}")  # Should reuse above
        d3 = ctx.build_expression("{{ b }}")  # Should not reuse above

        assert d1 is d2
        assert d1 is not d3

    def should_not_reuse_previous_value_of_dynamic_template_var(
        create_context: ContextCreator,
    ) -> None:
        ctx, _ = create_context()

        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "{{ now() }}")
        d1 = ctx.build_expression("{{ b }}")
        with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
            d2 = ctx.build_expression("{{ b }}")
        d3 = ctx.build_expression("{{ b }}")

        assert d1 is not d2
        assert d1 is not d3
        assert d2 is not d3

    def should_not_cache_bare_expressions(create_context: ContextCreator) -> None:
        ctx, _ = create_context()

        with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
            d1 = ctx.build_expression("{{ now() }}")
            d2 = ctx.build_expression("{{ now() }}")

        assert d1 is not d2

    def should_not_reuse_outer_cache(create_context: ContextCreator) -> None:
        ctx, _ = create_context()

        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "{{ now() }}")
        with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
            do1 = ctx.build_expression("{{ b }}")
            with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
                di1 = ctx.build_expression("{{ b }}")
                di2 = ctx.build_expression("{{ b }}")
            do2 = ctx.build_expression("{{ b }}")

        assert di1 is di2
        assert do1 is do2
        assert di1 is not do1

    def should_cache_nested_variables(create_context: ContextCreator) -> None:
        ctx, _ = create_context()

        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "{{ now() }}")
        ctx.define_initialised_variable("a", EnvironmentType.HOST_FACTS, "{{ b }}")
        with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
            d1 = ctx.build_expression("{{ a }}")
            d2 = ctx.build_expression("{{ a }}")

        assert d1 is d2

    def should_reuse_variables_in_different_expressions(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.define_initialised_variable("b", EnvironmentType.HOST_FACTS, "{{ now() }}")
        with ctx.enter_cached_scope(EnvironmentType.TASK_VARS):
            ctx.build_expression("{{ b + 1 }}")
            ctx.build_expression("{{ b + 2 }}")

        assert_graphs_match(
            g,
            create_graph(
                {
                    "b": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=EnvironmentType.HOST_FACTS.value,
                    ),
                    "be": Expression(expr="{{ now() }}"),
                    "bei": IntermediateValue(identifier=0),
                    "e1": Expression(expr="{{ b + 1 }}"),
                    "e2": Expression(expr="{{ b + 2 }}"),
                    "ei1": IntermediateValue(identifier=1),
                    "ei2": IntermediateValue(identifier=2),
                },
                {
                    ("be", "bei", DEF),
                    ("bei", "b", DEF),
                    ("b", "e1", USE),
                    ("b", "e2", USE),
                    ("e1", "ei1", DEF),
                    ("e2", "ei2", DEF),
                },
            ),
        )
