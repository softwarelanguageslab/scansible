# pyright: reportUnusedFunction = false

from __future__ import annotations

from scansible.representations.pdg.extractor.expressions.environments import (
    EnvironmentStack,
    EnvironmentType,
)
from scansible.representations.pdg.extractor.expressions.records import (
    VariableDefinitionRecord,
)
from scansible.utils import SENTINEL


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
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.set_variable_definition(
            "test2",
            VariableDefinitionRecord(
                "test2", 0, "{{ 3 + 4 }}", EnvironmentType.INCLUDE_VARS
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {
            "test1": "{{ 1 + 1 }}",
            "test2": "{{ 3 + 4 }}",
        }

    def should_return_highest_precedence_vars() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, "{{ 3 + 4 }}", EnvironmentType.INCLUDE_VARS
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {
            "test1": "{{ 3 + 4 }}",
        }

    def should_return_highest_precedence_vars_in_different_order() -> None:
        env_stack = EnvironmentStack()
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 0, "{{ 3 + 4 }}", EnvironmentType.INCLUDE_VARS
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {
            "test1": "{{ 3 + 4 }}",
        }

    def should_return_highest_precedence_vars_in_nested_environments() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, "{{ 3 + 4 }}", EnvironmentType.TASK_VARS
            ),
        )

        result = env_stack.get_variable_initialisers()

        assert result == {
            "test1": "{{ 3 + 4 }}",
        }

    def should_not_return_variables_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord("test1", 0, SENTINEL, EnvironmentType.TASK_VARS),
        )

        result = env_stack.get_variable_initialisers()

        assert not result

    def should_not_return_variables_overridden_by_ones_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, SENTINEL, EnvironmentType.SET_FACTS_REGISTERED
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
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.set_variable_definition(
            "test2",
            VariableDefinitionRecord(
                "test2", 0, "{{ 3 + 4 }}", EnvironmentType.INCLUDE_VARS
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
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, "{{ 3 + 4 }}", EnvironmentType.INCLUDE_VARS
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 1)}

    def should_return_highest_precedence_vars_in_different_order() -> None:
        env_stack = EnvironmentStack()
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 0, "{{ 3 + 4 }}", EnvironmentType.INCLUDE_VARS
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
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
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, "{{ 3 + 4 }}", EnvironmentType.TASK_VARS
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 1)}

    def should_return_variables_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord("test1", 0, SENTINEL, EnvironmentType.TASK_VARS),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 0)}

    def should_return_variables_overridden_by_ones_without_initialisers() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 0, "{{ 1 + 1 }}", EnvironmentType.TASK_VARS
            ),
        )
        env_stack.set_variable_definition(
            "test1",
            VariableDefinitionRecord(
                "test1", 1, SENTINEL, EnvironmentType.SET_FACTS_REGISTERED
            ),
        )

        result = env_stack.get_currently_visible_definitions()

        assert result == {("test1", 1)}
