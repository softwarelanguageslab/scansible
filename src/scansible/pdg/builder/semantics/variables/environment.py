from __future__ import annotations

from typing import Literal, final, get_args, override

import abc
import operator
from collections import defaultdict
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from enum import Enum
from functools import reduce
from itertools import chain

from loguru import logger

from scansible import ast
from scansible.pdg import representation as rep
from scansible.pdg.representation import NodeLocation, Variable
from scansible.utils import first, first_where

from .constants import MAGIC_VAR_NAMES, UNQUALIFIED_HOST_FACT_NAMES


class EnvironmentType(Enum):
    """Possible environment types.

    Element's value is the precedence level, higher wins.
    """

    UNDEFINED = -1
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
    MAGIC_VARS = 22  # Undocumented, take highest precedence


type LocalEnvType = Literal[
    EnvironmentType.TASK_VARS,
    EnvironmentType.BLOCK_VARS,
    EnvironmentType.ROLE_PARAMS,
    EnvironmentType.INCLUDE_PARAMS,
    # Following pop after the play is done.
    EnvironmentType.PLAY_VARS,
    EnvironmentType.PLAY_VARS_FILES,
    EnvironmentType.PLAY_VARS_PROMPT,
    # Role vars and defaults can pop depending on certain conditions, such as
    # the `private_role_vars` Ansible configuration, whether the role include
    # carries a `public: true` directive, whether it's a play role, import_role,
    # or include_role, etc.
    EnvironmentType.ROLE_DEFAULTS,
    EnvironmentType.ROLE_VARS,
]


"""Environments which can be stacked, i.e., for which a new environment can be created and destroyed."""
LOCAL_ENV_TYPES: set[EnvironmentType] = set(get_args(LocalEnvType.__value__))  # pyright: ignore[reportAny]

"""Environments which cannot be stacked."""
GLOBAL_ENV_TYPES = set(EnvironmentType) - LOCAL_ENV_TYPES


@dataclass(frozen=True)
class VariableDefinitionRecord:
    """Binding of a variable at any given time."""

    name: str
    revision: int
    #: The initialiser expression, or the constant variable node if this variable is defined with a value (e.g., facts and `register`ed variables).
    value: ast.AnyExpression | rep.Variable
    env_type: EnvironmentType
    #: Data nodes representing conditions under which this variable is defined.
    conditions: Sequence[rep.DataNode]
    #: The location where the variable is defined.
    location: rep.NodeLocation


class Environment(abc.ABC):
    """Ansible environment, mapping names to variable definition records."""

    def __init__(self, env_type: EnvironmentType) -> None:
        self.env_type: EnvironmentType = env_type

    @override
    def __str__(self) -> str:
        return f"{self.__class__.__name__}(env_type={self.env_type.name})"

    @abc.abstractmethod
    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        """Get the definition of the given variable in this environment, or None if not present."""
        ...

    @abc.abstractmethod
    def set_variable_definition(self, rec: VariableDefinitionRecord) -> None:
        """Add the variable definition to this environment."""
        ...

    @abc.abstractmethod
    def has_variable_definition(self, name: str, revision: int) -> bool:
        """Check whether a variable with the given name and revision exist in this environment."""
        ...

    @abc.abstractmethod
    def get_all_variable_definitions(self) -> dict[str, VariableDefinitionRecord]:
        """Get all variable definitions in this environment."""
        ...


class GenericEnvironment(Environment):
    """Generic Ansible environment allowing variables to be defined and retrieved."""

    def __init__(self, env_type: EnvironmentType) -> None:
        super().__init__(env_type)
        # Variables defined in this scope.
        self._var_def_store: dict[str, VariableDefinitionRecord] = {}

    @override
    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        return self._var_def_store.get(name)

    @override
    def set_variable_definition(self, rec: VariableDefinitionRecord) -> None:
        self._var_def_store[rec.name] = rec

    @override
    def has_variable_definition(self, name: str, revision: int) -> bool:
        return (
            name in self._var_def_store
            and self._var_def_store[name].revision == revision
        )

    @override
    def get_all_variable_definitions(self) -> dict[str, VariableDefinitionRecord]:
        return dict(self._var_def_store)


class _InjectedVariablesEnvironment(Environment, abc.ABC):
    """Environment for variables that are automatically injected by the Ansible runtime.

    This environment responds to all requests for the names it manages but does not store
    any other variables.

    Clients should override `_is_injected_variable` to return True for all variables that
    should be managed.
    """

    def __init__(self, env_type: EnvironmentType) -> None:
        super().__init__(env_type)
        # Cache of previous responses
        self._var_def_store: dict[str, VariableDefinitionRecord] = {}

    @abc.abstractmethod
    def _is_injected_variable(self, name: str) -> bool: ...

    @override
    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        if not self._is_injected_variable(name):
            return None

        if name not in self._var_def_store:
            # Create and save a record so we'll always return the same constant. We'll also
            # create a variable node so that all references to this magic var will use the
            # same variable node. The expression builder will add this node when required.
            var_node = Variable(
                name=name, version=0, value_version=0, scope_level=self.env_type.value
            )
            self._var_def_store[name] = VariableDefinitionRecord(
                name, 0, var_node, self.env_type, [], NodeLocation.synthetic()
            )

        return self._var_def_store[name]

    @override
    def set_variable_definition(self, rec: VariableDefinitionRecord) -> None:
        raise ValueError("Cannot set an injected variable")

    @override
    def has_variable_definition(self, name: str, revision: int) -> bool:
        return self._is_injected_variable(name)

    @override
    def get_all_variable_definitions(self) -> dict[str, VariableDefinitionRecord]:
        # Only the vars that have been dereferenced at this point.
        return dict(self._var_def_store)


class MagicVariablesEnvironment(_InjectedVariablesEnvironment):
    """Environment for magic variables."""

    @override
    def _is_injected_variable(self, name: str) -> bool:
        return name in MAGIC_VAR_NAMES


class HostFactEnvironment(_InjectedVariablesEnvironment):
    """Environment for host facts."""

    @override
    def _is_injected_variable(self, name: str) -> bool:
        # Approximate: There are a lot of host facts, but they should always start
        # with "ansible_". This is only called for undefined variable names anyway.
        return name in UNQUALIFIED_HOST_FACT_NAMES or name.startswith("ansible_")


_ENV_FACTORY = defaultdict[EnvironmentType, Callable[[EnvironmentType], Environment]](
    lambda: GenericEnvironment,
    {
        EnvironmentType.HOST_FACTS: HostFactEnvironment,
        EnvironmentType.MAGIC_VARS: MagicVariablesEnvironment,
    },
)


def _make_environment(level: EnvironmentType) -> Environment:
    return _ENV_FACTORY[level](level)


@final
class EnvironmentStack:
    """Collection of variable environments, enabling variable definition and lookup, and environment iteration."""

    def __init__(self) -> None:
        global_env_order = sorted(GLOBAL_ENV_TYPES, key=operator.attrgetter("value"))
        self._global_environments = tuple(map(_make_environment, global_env_order))
        self._local_environment_stack: list[Environment] = []

    @property
    def environment_stack(self) -> Sequence[Environment]:
        """Sequence of all environments in stacking order, from most global to most local environment."""
        return tuple(chain(self._global_environments, self._local_environment_stack))

    @property
    def precedence_chain(self) -> Sequence[Environment]:
        """Sequence of all environments in precendence order, with earlier environments getting higher precedence."""
        return self._calculate_precedence_chain(self.environment_stack)

    def _calculate_precedence_chain(
        self, environments: Sequence[Environment]
    ) -> Sequence[Environment]:
        return sorted(environments, key=lambda scope: scope.env_type.value)[::-1]

    @property
    def top_environment(self) -> Environment:
        """Top-most (most local) environment."""
        return self.environment_stack[-1]

    def _get_highest_precedence_variable_definition(
        self, key: str
    ) -> tuple[VariableDefinitionRecord, Environment] | None:
        return first(
            (el, env)
            for env in self.precedence_chain
            if (el := env.get_variable_definition(key)) is not None
        )

    def _get_topmost_environment(self, env_type: EnvironmentType) -> Environment:
        env = first_where(
            self.environment_stack[::-1], lambda env: env.env_type == env_type
        )
        if env is None:
            raise RuntimeError(
                "Attempting to access an environment which has not been entered"
            )
        return env

    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        """Look up and return the highest precedence variable definition for the given name, or None if not defined."""
        logger.debug(f"Looking up variable definition for {name!r}")
        result = self._get_highest_precedence_variable_definition(name)
        if result is None:
            logger.debug("Miss!")
            return None

        logger.debug(f"Hit! Found {result[0]!r} in {result[1]!r}")
        return result[0]

    def set_variable_definition(self, rec: VariableDefinitionRecord) -> None:
        """Define the given variable in the innermost environment."""
        self._get_topmost_environment(rec.env_type).set_variable_definition(rec)

    def _get_all_visible_definitions(self) -> dict[str, VariableDefinitionRecord]:
        return reduce(
            operator.or_,  # pyright: ignore[reportUnknownMemberType, reportUnknownArgumentType]
            (
                env.get_all_variable_definitions()
                for env in reversed(self.precedence_chain)
            ),
        )

    def get_currently_visible_definitions(self) -> set[tuple[str, int]]:
        """Get the set of all variable definitions that are in scope at this point in the evaluation."""
        all_vars = self._get_all_visible_definitions()
        return {(vdef.name, vdef.revision) for vdef in all_vars.values()}

    def enter_scope(self, env_type: LocalEnvType) -> None:
        """Enter a new environment of the given type and add it to the stack."""
        if env_type not in LOCAL_ENV_TYPES:
            raise ValueError("Attempted to enter a global environment")
        self._local_environment_stack.append(_make_environment(env_type))
        logger.debug(f"Entered {self.environment_stack[-1]}")

    def exit_scope(self) -> None:
        """Exit the most local environment and pop it from the stack."""
        logger.debug(f"Leaving {self.environment_stack[-1]}")
        _ = self._local_environment_stack.pop()
