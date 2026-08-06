from __future__ import annotations

from typing import override

import abc

from scansible.representations.pdg.extractor.expressions.constants import (
    MAGIC_VAR_NAMES,
    UNQUALIFIED_HOST_FACT_NAMES,
)
from scansible.representations.pdg.representation import NodeLocation, Variable

from ..records import VariableDefinitionRecord
from .types import EnvironmentType


class Environment(abc.ABC):
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
