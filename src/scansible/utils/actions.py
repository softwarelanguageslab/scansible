from __future__ import annotations

from ansible import constants
from ansible.utils.fqcn import add_internal_fqcns


def is_set_fact(action: str) -> bool:
    return action in constants._ACTION_SET_FACT  # pyright: ignore


def is_include_vars(action: str) -> bool:
    return action in constants._ACTION_INCLUDE_VARS  # pyright: ignore


def is_import_include_tasks(action: str) -> bool:
    return action in constants._ACTION_ALL_INCLUDE_IMPORT_TASKS or is_bare_include(
        action
    )  # pyright: ignore


def is_include_tasks(action: str) -> bool:
    return action in constants._ACTION_INCLUDE_TASKS  # pyright: ignore


def is_import_tasks(action: str) -> bool:
    return action in constants._ACTION_IMPORT_TASKS  # pyright: ignore


def is_import_include_role(action: str) -> bool:
    return (
        action in constants._ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES  # pyright: ignore
    )


def is_import_playbook(action: str) -> bool:
    return action in constants._ACTION_IMPORT_PLAYBOOK  # pyright: ignore


def is_bare_include(action: str) -> bool:
    return action in add_internal_fqcns(["include"])
