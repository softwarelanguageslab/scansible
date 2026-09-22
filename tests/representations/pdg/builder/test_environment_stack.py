# pyright: reportUnusedFunction = false

from __future__ import annotations

from scansible import ast
from scansible.pdg.builder.semantics.variables.environment import (
    EnvironmentStack,
    EnvironmentType,
    VariableDefinitionRecord,
)
from scansible.pdg.representation import NodeLocation


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
