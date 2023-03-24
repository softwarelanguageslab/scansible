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
    Literal,
    NodeLocation,
    Variable,
)
from scansible.representations.pdg.extractor.context import ExtractionContext
from scansible.representations.pdg.extractor.expressions import ScopeLevel, VarContext
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

        ctx.evaluate_template(expr, False)

        assert_graphs_match(
            g, create_graph({"lit": Literal(type="str", value=expr)}, [])
        )

    def should_declare_literal_variable(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.register_variable("test_var", ScopeLevel.PLAY_VARS, expr="hello world")

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit": Literal(type="str", value="hello world"),
                    "var": Variable(
                        "test_var", 0, 0, ScopeLevel.PLAY_VARS.value
                    ),  # UNUSED!
                },
                [("lit", "var", DEF)],
            ),
        )

    def should_extract_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.evaluate_template("hello {{ target }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "var": Variable(
                        name="target",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.CLI_VALUES.value,
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

    def should_reevaluate_template_literal(create_context: ContextCreator) -> None:
        # We don't want to deduplicate template literals yet
        ctx, g = create_context()

        ctx.evaluate_template("hello world", False)
        ctx.evaluate_template("hello world", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "lit1": Literal(type="str", value="hello world"),
                    "lit2": Literal(type="str", value="hello world"),
                },
                [],
            ),
        )

    def should_not_reevaluate_variables(create_context: ContextCreator) -> None:
        # We don't want to deduplicate template literals yet
        ctx, g = create_context()

        ctx.evaluate_template("hello {{ target }}", False)
        ctx.evaluate_template("hello {{ target }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "target": Variable(
                        name="target",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.CLI_VALUES.value,
                    ),
                    "expression": Expression(expr="hello {{ target }}"),
                    "iv": IntermediateValue(identifier=1),
                },
                [("target", "expression", USE), ("expression", "iv", DEF)],
            ),
        )

    def should_extract_variable_definition(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.register_variable("msg", ScopeLevel.PLAY_VARS, expr="hello {{ target }}")
        ctx.evaluate_template("{{ msg }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "target": Variable(
                        name="target",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.CLI_VALUES.value,
                    ),
                    "msg": Variable(
                        name="msg",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
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

        ctx.evaluate_template(expr, False)
        ctx.evaluate_template(expr, False)

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

        ctx.evaluate_template(expr, False)
        ctx.evaluate_template(expr, False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "e": Expression(expr=expr, non_idempotent_components=components),
                    "iv1": IntermediateValue(identifier=1),
                    "iv2": IntermediateValue(identifier=2),
                },
                [("e", "iv1", DEF), ("e", "iv2", DEF)],
            ),
        )

    def should_reevaluate_when_variable_changed(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="hello")
        ctx.evaluate_template("{{ a }} world", False)
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("a", ScopeLevel.TASK_VARS, expr="hi")
            ctx.evaluate_template("{{ a }} world", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a1": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "l1": Literal(type="str", value="hello"),
                    "e1": Expression(expr="{{ a }} world"),
                    "a2": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "l2": Literal(type="str", value="hi"),
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

        ctx.register_variable("when", ScopeLevel.PLAY_VARS, expr="{{ now() }}")
        ctx.evaluate_template("The time is {{ when }}", False)
        ctx.evaluate_template("The time is {{ when }}", False)

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
                        non_idempotent_components=("function 'now'",),
                    ),
                    "iv1": IntermediateValue(identifier=1),
                    "when1": Variable(
                        name="when",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "e2": e2,
                    "iv2": IntermediateValue(identifier=2),
                    "e3": e3,
                    "iv3": IntermediateValue(identifier=3),
                    "when2": Variable(
                        name="when",
                        version=0,
                        value_version=1,
                        scope_level=ScopeLevel.PLAY_VARS.value,
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="hello")
        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="{{ a }} world")
        ctx.evaluate_template("{{ b }}!", False)
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("a", ScopeLevel.TASK_VARS, expr="hi")
            ctx.evaluate_template("{{ b }}!", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a1": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "l1": Literal(type="str", value="hello"),
                    "b1": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "e1": Expression(expr="{{ a }} world"),
                    "i1": IntermediateValue(identifier=1),
                    "e2": Expression(expr="{{ b }}!"),
                    "i2": IntermediateValue(identifier=2),
                    "a2": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "l2": Literal(type="str", value="hi"),
                    "b2": Variable(
                        name="b",
                        version=0,
                        value_version=1,
                        scope_level=ScopeLevel.PLAY_VARS.value,
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="hello")
        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="world")
        ctx.evaluate_template("{{ a }} {{ b }}!", False)
        ctx.register_variable("a", ScopeLevel.PLAY_VARS_PROMPT, expr="hi")
        ctx.evaluate_template("{{ a }} {{ b }}!", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a1": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "l1": Literal(type="str", value="hello"),
                    "b": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "l2": Literal(type="str", value="world"),
                    "e1": Expression(expr="{{ a }} {{ b }}!"),
                    "i1": IntermediateValue(identifier=1),
                    "a2": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS_PROMPT.value,
                    ),
                    "l3": Literal(type="str", value="hi"),
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="1")
        ctx.evaluate_template("1 {{ a }}", False)
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("a", ScopeLevel.TASK_VARS, expr="2")
            ctx.evaluate_template("2 {{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "1": Literal(type="str", value="1"),
                    "e1": Expression(expr="1 {{ a }}"),
                    "iv1": IntermediateValue(identifier=1),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "2": Literal(type="str", value="2"),
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="1")
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("a", ScopeLevel.SET_FACTS_REGISTERED, expr="2")
        ctx.evaluate_template("{{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": Literal(type="str", value="1"),
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),  # UNUSED!
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.SET_FACTS_REGISTERED.value,
                    ),
                    "2": Literal(type="str", value="2"),
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

    def should_reuse_prev_outer_template_in_inner(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="1")
        ctx.evaluate_template("1 {{ a }}", False)
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.evaluate_template("1 {{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "1": Literal(type="str", value="1"),
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="1")
        ctx.evaluate_template("1 {{ a }}", False)
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("a", ScopeLevel.TASK_VARS, expr="2")
        ctx.evaluate_template("1 {{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),  # UNUSED!
                    "1": Literal(type="str", value="1"),
                    "2": Literal(type="str", value="2"),
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="1")
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("c", ScopeLevel.TASK_VARS, expr="c")
            ctx.evaluate_template("1 {{ a }}", False)
            ctx.register_variable("a", ScopeLevel.TASK_VARS, expr="2")
        ctx.evaluate_template("1 {{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "c": Variable(
                        name="c",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "1": Literal(type="str", value="1"),
                    "clit": Literal(type="str", value="c"),
                    "2": Literal(type="str", value="2"),
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
        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="1")
        ctx.evaluate_template("1 {{ a }}", False)
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("a", ScopeLevel.TASK_VARS, expr="2")
            ctx.evaluate_template("1 {{ a }}", False)
        ctx.evaluate_template("1 {{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "aouter": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "1": Literal(type="str", value="1"),
                    "e1": Expression(expr="1 {{ a }}"),
                    "iv1": IntermediateValue(identifier=1),
                    "ainner": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "2": Literal(type="str", value="2"),
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="{{ b }}")
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("b", ScopeLevel.TASK_VARS, expr="1")
            ctx.evaluate_template("{{ a }}", False)
        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="2")
        ctx.evaluate_template("{{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "ai": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "aei": Expression(expr="{{ b }}"),
                    "aeiv": IntermediateValue(identifier=0),
                    "binner": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "bil": Literal(type="str", value="1"),
                    "ei": Expression(expr="{{ a }}"),
                    "eiv": IntermediateValue(identifier=1),
                    "bouter": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "bol": Literal(type="str", value="2"),
                    "eo": Expression(expr="{{ a }}"),
                    "eov": IntermediateValue(identifier=2),
                    "ao": Variable(
                        name="a",
                        version=0,
                        value_version=1,
                        scope_level=ScopeLevel.PLAY_VARS.value,
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

        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable(
                "a", ScopeLevel.TASK_VARS, expr='{{ "hello" | reverse }}'
            )
            ctx.register_variable("b", ScopeLevel.TASK_VARS, expr="{{ c | reverse }}")
            ctx.register_variable("c", ScopeLevel.TASK_VARS, expr="world")
            ctx.evaluate_template("{{ b }} {{ a }}", False)
        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr='{{ "hello" | reverse }}')
        ctx.evaluate_template("{{ b }} {{ a }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "c": Variable(
                        name="c",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "cl": Literal(type="str", value="world"),
                    "bie": Expression(expr="{{ c | reverse }}"),
                    "biv": IntermediateValue(identifier=0),
                    "binner": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "ae": Expression(expr='{{ "hello" | reverse }}'),
                    "aiv": IntermediateValue(identifier=1),
                    "ai": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "ie": Expression(expr="{{ b }} {{ a }}"),
                    "iev": IntermediateValue(identifier=2),
                    "bouter": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.CLI_VALUES.value,
                    ),
                    "ao": Variable(
                        name="a",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
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

        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="{{ b }}")
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("b", ScopeLevel.TASK_VARS, expr="1")
            with ctx.enter_scope(ScopeLevel.TASK_VARS):
                ctx.evaluate_template("{{ a }}", False)
            ctx.evaluate_template("{{ a }}", False)  # Should reuse above expr

        assert_graphs_match(
            g,
            create_graph(
                {
                    "a": Variable(
                        name="a",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
                    ),
                    "b": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "lb": Literal(type="str", value="1"),
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

        vn = ctx.register_variable("b", ScopeLevel.SET_FACTS_REGISTERED)
        ln = Literal(type="int", value=1)
        g.add_node(ln)
        g.add_edge(ln, vn, DEF)
        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("b", ScopeLevel.TASK_VARS, expr="2")
            ctx.evaluate_template("{{ b }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": Literal(type="int", value=1),
                    "2": Literal(type="str", value="2"),
                    "bsf": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.SET_FACTS_REGISTERED.value,
                    ),
                    "bt": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
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

        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("b", ScopeLevel.TASK_VARS, expr="1")
        vn = ctx.register_variable("b", ScopeLevel.SET_FACTS_REGISTERED)
        ln = Literal(type="int", value=2)
        g.add_node(ln)
        g.add_edge(ln, vn, DEF)
        ctx.evaluate_template("{{ b }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": Literal(type="str", value="1"),
                    "2": Literal(type="int", value=2),
                    "binner": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "b": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.SET_FACTS_REGISTERED.value,
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

        with ctx.enter_scope(ScopeLevel.TASK_VARS):
            ctx.register_variable("b", ScopeLevel.TASK_VARS, expr="1")
            vn = ctx.register_variable("b", ScopeLevel.SET_FACTS_REGISTERED)
            ln = Literal(type="int", value=2)
            g.add_node(ln)
            g.add_edge(ln, vn, DEF)
            ctx.evaluate_template("{{ b }}", False)
        ctx.evaluate_template("{{ b }}", False)  # Should reuse above expr

        assert_graphs_match(
            g,
            create_graph(
                {
                    "1": Literal(type="str", value="1"),
                    "2": Literal(type="int", value=2),
                    "b1": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.TASK_VARS.value,
                    ),
                    "b": Variable(
                        name="b",
                        version=1,
                        value_version=0,
                        scope_level=ScopeLevel.SET_FACTS_REGISTERED.value,
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
        ctx, g = create_context()

        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="{{ now() }}")
        with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
            tr = ctx.evaluate_template("{{ b }}", False)
            tr2 = ctx.evaluate_template("{{ b }}", False)  # Should reuse above

        assert tr.data_node is tr2.data_node

    def should_discard_after_leaving_scope(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="{{ now() }}")
        with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
            tr = ctx.evaluate_template("{{ b }}", False)
            tr2 = ctx.evaluate_template("{{ b }}", False)  # Should reuse above
        tr3 = ctx.evaluate_template("{{ b }}", False)  # Should not reuse above

        assert tr.data_node is tr2.data_node
        assert tr.data_node is not tr3.data_node

    def should_not_reuse_previous_value_of_dynamic_template_var(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="{{ now() }}")
        tr1 = ctx.evaluate_template("{{ b }}", False)
        with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
            tr2 = ctx.evaluate_template("{{ b }}", False)
        tr3 = ctx.evaluate_template("{{ b }}", False)

        assert tr1.data_node is not tr2.data_node
        assert tr1.data_node is not tr3.data_node
        assert tr2.data_node is not tr3.data_node

    def should_not_cache_bare_expressions(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
            tr1 = ctx.evaluate_template("{{ now() }}", False)
            tr2 = ctx.evaluate_template("{{ now() }}", False)

        assert tr1.data_node is not tr2.data_node

    def should_not_reuse_outer_cache(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="{{ now() }}")
        with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
            tro1 = ctx.evaluate_template("{{ b }}", False)
            with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
                tri1 = ctx.evaluate_template("{{ b }}", False)
                tri2 = ctx.evaluate_template("{{ b }}", False)
            tro2 = ctx.evaluate_template("{{ b }}", False)

        assert tri1.data_node is tri2.data_node
        assert tro1.data_node is tro2.data_node
        assert tri1.data_node is not tro1.data_node

    def should_cache_nested_variables(create_context: ContextCreator) -> None:
        ctx, g = create_context()

        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="{{ now() }}")
        ctx.register_variable("a", ScopeLevel.PLAY_VARS, expr="{{ b }}")
        with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
            tr1 = ctx.evaluate_template("{{ a }}", False)
            tr2 = ctx.evaluate_template("{{ a }}", False)

        assert tr1.data_node is tr2.data_node

    def should_reuse_variables_in_different_expressions(
        create_context: ContextCreator,
    ) -> None:
        ctx, g = create_context()

        ctx.register_variable("b", ScopeLevel.PLAY_VARS, expr="{{ now() }}")
        with ctx.enter_cached_scope(ScopeLevel.TASK_VARS):
            ctx.evaluate_template("{{ b + 1 }}", False)
            ctx.evaluate_template("{{ b + 2 }}", False)

        assert_graphs_match(
            g,
            create_graph(
                {
                    "b": Variable(
                        name="b",
                        version=0,
                        value_version=0,
                        scope_level=ScopeLevel.PLAY_VARS.value,
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
