from __future__ import annotations

from typing import override

from ..records import VariableDefinitionRecord
from .types import EnvironmentType


class Environment:
    def __init__(self, env_type: EnvironmentType) -> None:
        self.env_type: EnvironmentType = env_type
        # Variables defined in this scope.
        self._var_def_store: dict[str, VariableDefinitionRecord] = {}

    @override
    def __str__(self) -> str:
        return f"Environment(env_type={self.env_type.name})"

    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        return self._var_def_store.get(name)

    def set_variable_definition(self, name: str, rec: VariableDefinitionRecord) -> None:
        self._var_def_store[name] = rec

    def has_variable_definition(self, name: str, revision: int) -> bool:
        return (
            name in self._var_def_store
            and self._var_def_store[name].revision == revision
        )

    def get_all_variable_definitions(self) -> dict[str, VariableDefinitionRecord]:
        return dict(self._var_def_store)
