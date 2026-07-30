# pyright: reportUnknownMemberType = false, reportPrivateUsage = false

from __future__ import annotations

from ansible import constants  # pyright: ignore[reportMissingTypeStubs]
from ansible.utils.fqcn import (  # pyright: ignore[reportMissingTypeStubs]
    add_internal_fqcns,  # pyright: ignore[reportUnknownVariableType]
)


def is_set_fact(action: str) -> bool:
    return action in constants._ACTION_SET_FACT


def is_include_vars(action: str) -> bool:
    return action in constants._ACTION_INCLUDE_VARS


def is_import_include_tasks(action: str) -> bool:
    return action in constants._ACTION_ALL_INCLUDE_IMPORT_TASKS or is_bare_include(
        action
    )


def is_include_tasks(action: str) -> bool:
    return action in constants._ACTION_INCLUDE_TASKS


def is_import_tasks(action: str) -> bool:
    return action in constants._ACTION_IMPORT_TASKS


def is_import_include_role(action: str) -> bool:
    return action in constants._ACTION_ALL_PROPER_INCLUDE_IMPORT_ROLES


def is_include_role(action: str) -> bool:
    return action in constants._ACTION_INCLUDE_ROLE


def is_import_playbook(action: str) -> bool:
    return action in constants._ACTION_IMPORT_PLAYBOOK


def is_bare_include(action: str) -> bool:
    return action in add_internal_fqcns(["include"])
