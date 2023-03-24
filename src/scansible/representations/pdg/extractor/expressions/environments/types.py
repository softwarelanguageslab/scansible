from __future__ import annotations

from typing import Literal, Union, get_args

from enum import Enum


class EnvironmentType(Enum):
    """Possible environment types.

    Element's value is the precedence level, higher wins.
    """

    CLI_VALUES = 0
    ROLE_DEFAULTS = 1
    INV_FILE_GROUP_VARS = 2
    INV_GROUP_VARS_ALL = 3
    PB_GROUP_VARS_ALL = 4
    INV_GROUP_VARS = 5
    PB_GROUP_VARS = 6
    INV_FILE_HOST_VARS = 7
    INV_HOST_VARS = 8
    PB_HOST_VARS = 9
    HOST_FACTS = 10
    PLAY_VARS = 11
    PLAY_VARS_PROMPT = 12
    PLAY_VARS_FILES = 13
    ROLE_VARS = 14
    BLOCK_VARS = 15
    TASK_VARS = 16
    INCLUDE_VARS = 17
    SET_FACTS_REGISTERED = 18  # set_fact and register
    ROLE_PARAMS = 19
    INCLUDE_PARAMS = 20
    EXTRA_VARS = 21


LocalEnvType = Union[
    Literal[EnvironmentType.TASK_VARS],
    Literal[EnvironmentType.BLOCK_VARS],
    Literal[EnvironmentType.ROLE_PARAMS],
    Literal[EnvironmentType.INCLUDE_PARAMS],
    # Following pop after the play is done.
    Literal[EnvironmentType.PLAY_VARS],
    Literal[EnvironmentType.PLAY_VARS_FILES],
    Literal[EnvironmentType.PLAY_VARS_PROMPT],
    # Role vars and defaults can pop depending on certain conditions, such as
    # the `private_role_vars` Ansible configuration, whether the role include
    # carries a `public: true` directive, whether it's a play role, import_role,
    # or include_role, etc.
    Literal[EnvironmentType.ROLE_DEFAULTS],
    Literal[EnvironmentType.ROLE_VARS],
]


"""Environments which can be stacked, i.e., for which a new environment can be created and destroyed."""
LOCAL_ENV_TYPES = set(get_args(lit)[0] for lit in get_args(LocalEnvType))

"""Environments which cannot be stacked."""
GLOBAL_ENV_TYPES = set(EnvironmentType) - LOCAL_ENV_TYPES
