from __future__ import annotations

from typing import Iterable

from ..records import TemplateRecord, VariableDefinitionRecord, VariableValueRecord
from .types import EnvironmentType


class Environment:
    def __init__(self, env_type: EnvironmentType, is_cached: bool = False) -> None:
        self.env_type = env_type
        self.is_cached = is_cached
        self.cached_results: dict[str, VariableValueRecord] = {}
        # Values of expressions valid in this scope.
        self._expr_store: dict[str, TemplateRecord] = {}
        # Variables defined in this scope.
        self._var_def_store: dict[str, VariableDefinitionRecord] = {}
        # Values of variables in this scope. Variable itself can come from an
        # outer scope, but its value may depend on variables defined within
        # this scope.
        self._var_val_store: dict[str, VariableValueRecord] = {}

    def __repr__(self) -> str:
        return f"Environment(level={self.env_type.name}, is_cached={self.is_cached})"

    def get_variable_definition(self, name: str) -> VariableDefinitionRecord | None:
        return self._var_def_store.get(name)

    def set_variable_definition(self, name: str, rec: VariableDefinitionRecord) -> None:
        self._var_def_store[name] = rec

    def has_variable_definition(self, name: str, revision: int) -> bool:
        return (
            name in self._var_def_store
            and self._var_def_store[name].revision == revision
        )

    def get_variable_value(self, name: str) -> VariableValueRecord | None:
        return self._var_val_store.get(name)

    def set_variable_value(self, name: str, rec: VariableValueRecord) -> None:
        self._var_val_store[name] = rec

    def has_variable_value(self, name: str, def_rev: int, val_rev: int) -> bool:
        return (
            name in self._var_val_store
            and self._var_val_store[name].revision == def_rev
            and self._var_val_store[name].value_revision == val_rev
        )

    def get_all_variable_definitions(self) -> dict[str, VariableDefinitionRecord]:
        return dict(self._var_def_store)

    def get_cached_expression_evaluation(self, expr: str) -> TemplateRecord | None:
        return self._expr_store.get(expr)

    def set_cached_expression_evaluation(self, expr: str, rec: TemplateRecord) -> None:
        self._expr_store[expr] = rec

    def has_cached_expression_evaluation(self, expr: str) -> bool:
        return expr in self._expr_store

    def __str__(self) -> str:
        header = f"Environment@{self.env_type.name}"

        def join_strings(strings: Iterable[str]) -> str:
            return ", ".join(strings) or "none"

        locals_str = join_strings(
            f"{var_def.name}@{var_def.revision}"
            for var_def in self._var_def_store.values()
        )
        values_str = join_strings(
            f"{var_val.name}@{var_val.revision}.{var_val.value_revision}"
            for var_val in self._var_val_store.values()
        )
        exprs_str = join_strings(
            expr.expr_node.expr + (" (impure)" if expr.may_be_impure else "")
            for expr in self._expr_store.values()
            if not expr.is_literal
        )

        return f"{header} (locals: {locals_str}, values: {values_str}, expressions: {exprs_str})"
