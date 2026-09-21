# pyright: reportUnusedFunction = false

from __future__ import annotations

from scansible import ast
from scansible.pdg.builder.semantics.variables.environment import (
    EnvironmentStack,
    EnvironmentType,
    VariableDefinitionRecord,
)
from scansible.pdg.representation import NodeLocation, Variable

expr = ast.Expression.model_validate

FAKE_LOC = NodeLocation(file="test", line=1, column=1)
FAKE_VAR = Variable(name="test", version=0, value_version=0, scope_level=0)


def _mk_record(name: str, env_type: EnvironmentType) -> VariableDefinitionRecord:
    return VariableDefinitionRecord(
        name, 0, ast.StrLiteral("test"), env_type, [], NodeLocation.synthetic()
    )


def describe_scoping():
    def should_return_highest_precedence_variable():
        env_stack = EnvironmentStack()
        v1 = _mk_record("a", EnvironmentType.PB_GROUP_VARS)
        v2 = _mk_record("a", EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(v1)
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(v2)

        result = env_stack.get_variable_definition("a")

        assert result is v2

    def should_set_variables_in_correct_scope():
        env_stack = EnvironmentStack()
        v1 = _mk_record("a", EnvironmentType.PB_GROUP_VARS)
        v2 = _mk_record("a", EnvironmentType.SET_FACTS_REGISTERED)
        env_stack.set_variable_definition(v1)
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(v2)

        result = env_stack.get_variable_definition("a")

        assert result is v2

    def should_ignore_variables_in_exited_environment():
        env_stack = EnvironmentStack()
        v = _mk_record("a", EnvironmentType.TASK_VARS)
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(v)
        env_stack.exit_scope()

        result = env_stack.get_variable_definition("a")

        assert result is None

    def should_support_nested_environments():
        env_stack = EnvironmentStack()
        v = _mk_record("a", EnvironmentType.BLOCK_VARS)
        env_stack.enter_scope(EnvironmentType.BLOCK_VARS)
        env_stack.enter_scope(EnvironmentType.BLOCK_VARS)
        env_stack.set_variable_definition(v)

        result = env_stack.get_variable_definition("a")

        assert result is v

    def should_retrieve_variable_from_outer_nested_environment():
        env_stack = EnvironmentStack()
        v = _mk_record("a", EnvironmentType.BLOCK_VARS)
        env_stack.enter_scope(EnvironmentType.BLOCK_VARS)
        env_stack.set_variable_definition(v)
        env_stack.enter_scope(EnvironmentType.BLOCK_VARS)

        result = env_stack.get_variable_definition("a")

        assert result is v

    def should_ignore_variables_in_exited_nested_environments():
        env_stack = EnvironmentStack()
        v = _mk_record("a", EnvironmentType.BLOCK_VARS)
        env_stack.enter_scope(EnvironmentType.BLOCK_VARS)
        env_stack.enter_scope(EnvironmentType.BLOCK_VARS)
        env_stack.set_variable_definition(v)
        env_stack.exit_scope()

        result = env_stack.get_variable_definition("a")

        assert result is None

    def should_define_magic_variables():
        env_stack = EnvironmentStack()

        vdef = env_stack.get_variable_definition("ansible_version")

        assert vdef is not None
        assert vdef.env_type == EnvironmentType.MAGIC_VARS

    def should_return_same_magic_variable():
        env_stack = EnvironmentStack()

        v1 = env_stack.get_variable_definition("ansible_version")
        v2 = env_stack.get_variable_definition("ansible_version")

        assert v1 is v2

    def should_define_host_facts():
        env_stack = EnvironmentStack()

        vdef = env_stack.get_variable_definition("ansible_os_family")

        assert vdef is not None
        assert vdef.env_type == EnvironmentType.HOST_FACTS

    def should_return_same_host_fact():
        env_stack = EnvironmentStack()

        v1 = env_stack.get_variable_definition("ansible_os_family")
        v2 = env_stack.get_variable_definition("ansible_os_family")

        assert v1 is v2

    def should_override_host_facts_with_higher_precedence_definition():
        env_stack = EnvironmentStack()
        vdef = _mk_record("ansible_os_family", EnvironmentType.SET_FACTS_REGISTERED)
        env_stack.set_variable_definition(vdef)

        result = env_stack.get_variable_definition("ansible_os_family")

        assert result is vdef

    def should_not_override_host_facts_with_lower_precedence_definition():
        env_stack = EnvironmentStack()
        vdef = _mk_record("ansible_os_family", EnvironmentType.CLI_VALUES)
        env_stack.set_variable_definition(vdef)

        result = env_stack.get_variable_definition("ansible_os_family")

        assert result is not None
        assert result.env_type == EnvironmentType.HOST_FACTS


def describe_get_visible_definitions() -> None:
    def should_return_empty_when_no_vars_exist() -> None:
        env_stack = EnvironmentStack()

        result = env_stack.get_currently_visible_definitions()

        assert not result

    def should_return_all_vars_in_all_envs() -> None:
        env_stack = EnvironmentStack()
        env_stack.enter_scope(EnvironmentType.TASK_VARS)
        env_stack.set_variable_definition(
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
