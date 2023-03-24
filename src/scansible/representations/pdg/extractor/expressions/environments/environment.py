from __future__ import annotations

from scansible.utils import Sentinel

from ..records import TemplateRecord, VariableDefinitionRecord, VariableValueRecord
from .types import EnvironmentType


class Environment:
    def __init__(self, level: EnvironmentType, is_cached: bool = False) -> None:
        self.level = level
        self.is_cached = is_cached
        self.cached_results: dict[str, VariableValueRecord] = {}
        # Values of expressions valid in this scope
        self._expr_store: dict[str, TemplateRecord] = {}
        # Variables defined in this scope
        self._var_def_store: dict[str, VariableDefinitionRecord] = {}
        # Values of variables in this scope. Variable itself can come from an
        # outer scope, but its value may depend on variables defined within
        # this scope
        self._var_val_store: dict[str, VariableValueRecord] = {}

    def __repr__(self) -> str:
        return f"Scope(level={self.level.name}, is_cached={self.is_cached})"

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

    def get_var_mapping(self) -> dict[str, str]:
        return {
            vr.name: vr.template_expr
            for vr in self._var_def_store.values()
            if not isinstance(vr.template_expr, Sentinel)
        }

    def get_all_defined_variables(self) -> dict[str, int]:
        return {vr.name: vr.revision for vr in self._var_def_store.values()}

    def get_expression(self, expr: str) -> TemplateRecord | None:
        return self._expr_store.get(expr)

    def set_expression(self, expr: str, rec: TemplateRecord) -> None:
        self._expr_store[expr] = rec

    def has_expression(self, expr: str) -> bool:
        return expr in self._expr_store

    def __str__(self) -> str:
        out = "Scope@" + self.level.name
        locals_str = (
            ", ".join(f"{v.name}@{v.revision}" for v in self._var_def_store.values())
            or "none"
        )
        values_str = (
            ", ".join(
                f"{v.name}@{v.revision}.{v.value_revision}"
                for v in self._var_val_store.values()
            )
            or "none"
        )
        exprs_str = (
            ", ".join(
                e.expr_node.expr + (" (dynamic)" if e.may_be_dynamic else "")
                for e in self._expr_store.values()
                if not e.is_literal
            )
            or "none"
        )
        return f"{out} (locals: {locals_str}, values: {values_str}, expressions: {exprs_str})"
