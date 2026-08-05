# pyright: reportUnusedFunction = false

from __future__ import annotations

from scansible.representations import ast
from scansible.representations.pdg.extractor.expressions.environments import (
    EnvironmentStack,
    EnvironmentType,
)
from scansible.representations.pdg.extractor.expressions.records import (
    VariableDefinitionRecord,
)
from scansible.representations.pdg.representation import NodeLocation, Variable

expr = ast.Expression.model_validate

FAKE_LOC = NodeLocation(file="test", line=1, column=1)
FAKE_VAR = Variable(name="test", version=0, value_version=0, scope_level=0)


def describe_get_variable_initialisers() -> None:
    def should_return_empty_dict_when_no_vars_exist() -> None:
        env_stack = EnvironmentStack()

        result = env_stack.get_variable_initialisers()

        assert not result

    def should_return_all_vars_in_all_envs() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.set_variable_definition(
            "test2",
            VariableDefinitionRecord(
                "test2",
                0,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.INCLUDE_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {"test1": expr("{{ 1 + 1 }}"), "test2": expr("{{ 3 + 4 }}")}

    def should_return_highest_precedence_vars() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.INCLUDE_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {"test1": expr("{{ 3 + 4 }}")}

    def should_return_highest_precedence_vars_in_different_order() -> None:
        env_stack = EnvironmentStack()
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.INCLUDE_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {"test1": expr("{{ 3 + 4 }}")}

    def should_return_highest_precedence_vars_in_nested_environments() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {"test1": expr("{{ 3 + 4 }}")}

    def should_not_return_variables_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                FAKE_VAR,
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert not result

    def should_not_return_variables_overridden_by_ones_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                FAKE_VAR,
                env_type=EnvironmentType.SET_FACTS_REGISTERED,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert not result


def describe_get_visible_definitions() -> None:
    def should_return_empty_when_no_vars_exist() -> None:
        env_stack = EnvironmentStack()

        result = env_stack.get_currently_visible_definitions()

        assert not result

    def should_return_all_vars_in_all_envs() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.set_variable_definition(
            "test2",
            VariableDefinitionRecord(
                "test2",
                0,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.INCLUDE_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 0), ("test2", 0)}

    def should_return_highest_precedence_vars() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.INCLUDE_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 1)}

    def should_return_highest_precedence_vars_in_different_order() -> None:
        env_stack = EnvironmentStack()
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.INCLUDE_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 0)}

    def should_return_highest_precedence_vars_in_nested_environments() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                expr("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                expr("{{ 3 + 4 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 1)}

    def should_return_variables_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                FAKE_VAR,
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 0)}

    def should_return_variables_overridden_by_ones_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                0,
                ast.Expression.model_validate("{{ 1 + 1 }}"),
                env_type=EnvironmentType.TASK_VARS,
                conditions=[],
                location=FAKE_LOC,
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1",
                1,
                FAKE_VAR,
                env_type=EnvironmentType.SET_FACTS_REGISTERED,
                conditions=[],
                location=FAKE_LOC,
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 1)}
