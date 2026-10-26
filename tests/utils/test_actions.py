# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scansible.utils import actions

if TYPE_CHECKING:
    from collections.abc import Callable

_PREDICATES: dict[str, Callable[[str], bool]] = {
    "set_fact": actions.is_set_fact,
    "include_vars": actions.is_include_vars,
    "include_tasks": actions.is_include_tasks,
    "import_tasks": actions.is_import_tasks,
    "include_role": actions.is_include_role,
    "import_playbook": actions.is_import_playbook,
    "include": actions.is_bare_include,
}


def describe_add_internal_collection_prefixes() -> None:
    def should_expand_unqualified_name() -> None:
        assert actions.add_internal_collection_prefixes("debug") == {
            "debug",
            "ansible.builtin.debug",
            "ansible.legacy.debug",
        }

    def should_leave_qualified_name_alone() -> None:
        assert actions.add_internal_collection_prefixes("ansible.builtin.debug") == {
            "ansible.builtin.debug"
        }


def describe_simple_predicates() -> None:
    @pytest.mark.parametrize(("name", "predicate"), _PREDICATES.items())
    def should_match_unqualified_and_builtin_fqcns(
        name: str, predicate: Callable[[str], bool]
    ) -> None:
        assert predicate(name)
        assert predicate(f"ansible.builtin.{name}")
        assert predicate(f"ansible.legacy.{name}")

    @pytest.mark.parametrize(("name", "predicate"), _PREDICATES.items())
    def should_reject_other_actions(
        name: str, predicate: Callable[[str], bool]
    ) -> None:
        assert not predicate("debug")
        assert not predicate(f"community.general.{name}")
        for other in _PREDICATES.keys() - {name}:
            assert not predicate(other)


def describe_is_import_include_tasks() -> None:
    @pytest.mark.parametrize("action", ["include_tasks", "import_tasks", "include"])
    def should_accept_tasks_and_bare_include(action: str) -> None:
        assert actions.is_import_include_tasks(action)
        assert actions.is_import_include_tasks(f"ansible.builtin.{action}")

    @pytest.mark.parametrize("action", ["debug", "include_role", "import_playbook"])
    def should_reject_other_actions(action: str) -> None:
        assert not actions.is_import_include_tasks(action)


def describe_is_import_include_role() -> None:
    @pytest.mark.parametrize("action", ["include_role", "import_role"])
    def should_accept_both_role_actions(action: str) -> None:
        assert actions.is_import_include_role(action)
        assert actions.is_import_include_role(f"ansible.builtin.{action}")

    @pytest.mark.parametrize(
        "action", ["debug", "include", "import_playbook", "include_tasks"]
    )
    def should_reject_non_role_actions(action: str) -> None:
        assert not actions.is_import_include_role(action)


def describe_is_freeform_action() -> None:
    @pytest.mark.parametrize(
        "action",
        ["shell", "ansible.builtin.command", "ansible.windows.win_command", "raw"],
    )
    def should_match_freeform_actions(action: str) -> None:
        assert actions.is_freeform_action(action)

    @pytest.mark.parametrize(
        "action", ["debug", "ansible.builtin.debug", "community.general.shell"]
    )
    def should_reject_non_freeform_actions(action: str) -> None:
        assert not actions.is_freeform_action(action)
