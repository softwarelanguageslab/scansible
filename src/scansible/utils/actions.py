from __future__ import annotations

import itertools

from scansible.constants import BUILTIN_COLLECTION_NAMES


def add_internal_collection_prefixes(action: str) -> set[str]:
    """Prepend Ansible's internal collections to an action name.

    Adapted from `ansible.utils.fqcn.add_internal_fqcns`.
    """
    result = {action}
    if "." not in action:
        result |= {f"{collection}.{action}" for collection in BUILTIN_COLLECTION_NAMES}
    return result


_ACTION_INCLUDE = add_internal_collection_prefixes("include")
_ACTION_IMPORT_PLAYBOOK = add_internal_collection_prefixes("import_playbook")
_ACTION_IMPORT_ROLE = add_internal_collection_prefixes("import_role")
_ACTION_IMPORT_TASKS = add_internal_collection_prefixes("import_tasks")
_ACTION_INCLUDE_ROLE = add_internal_collection_prefixes("include_role")
_ACTION_INCLUDE_TASKS = add_internal_collection_prefixes("include_tasks")
_ACTION_INCLUDE_VARS = add_internal_collection_prefixes("include_vars")
_ACTION_SET_FACT = add_internal_collection_prefixes("set_fact")
_ACTION_ALL_PROPER_INCLUDE_IMPORT_TASKS = _ACTION_INCLUDE_TASKS | _ACTION_IMPORT_TASKS
_ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES = _ACTION_INCLUDE_ROLE | _ACTION_IMPORT_ROLE
#: Unqualified names of actions that take freeform (unparsed) arguments.
_FREEFORM_ACTIONS_SIMPLE = (
    "command",
    "raw",
    "script",
    "shell",
    "win_command",
    "win_shell",
)
#: `FREEFORM_ACTIONS_SIMPLE`, expanded with their fully-qualified collection names.
_FREEFORM_ACTIONS: frozenset[str] = frozenset(
    set(
        itertools.chain(
            *map(add_internal_collection_prefixes, _FREEFORM_ACTIONS_SIMPLE)
        )
    )
    | {"ansible.windows.win_command", "ansible.windows.win_shell"}
)


def is_set_fact(action: str) -> bool:
    return action in _ACTION_SET_FACT


def is_include_vars(action: str) -> bool:
    return action in _ACTION_INCLUDE_VARS


def is_import_include_tasks(action: str) -> bool:
    return action in _ACTION_ALL_PROPER_INCLUDE_IMPORT_TASKS or is_bare_include(action)


def is_include_tasks(action: str) -> bool:
    return action in _ACTION_INCLUDE_TASKS


def is_import_tasks(action: str) -> bool:
    return action in _ACTION_IMPORT_TASKS


def is_import_include_role(action: str) -> bool:
    return action in _ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES


def is_include_role(action: str) -> bool:
    return action in _ACTION_INCLUDE_ROLE


def is_import_playbook(action: str) -> bool:
    return action in _ACTION_IMPORT_PLAYBOOK


def is_bare_include(action: str) -> bool:
    return action in _ACTION_INCLUDE


def is_freeform_action(action: str) -> bool:
    return action in _FREEFORM_ACTIONS
