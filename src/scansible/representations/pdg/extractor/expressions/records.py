from __future__ import annotations

from typing import NamedTuple

from scansible.utils import Sentinel

from ... import representation as rep


class TemplateRecord(NamedTuple):
    """State of a template expression."""

    data_node: rep.DataNode
    expr_node: rep.Expression
    used_variables: list[tuple[str, int, int]]
    is_literal: bool

    @property
    def may_be_impure(self) -> bool:
        return not self.expr_node.idempotent

    def __repr__(self) -> str:
        return f"TemplateRecord(expr={self.expr_node.expr!r}, data_node={self.data_node.node_id}, expr_node={self.expr_node.node_id})"


class VariableDefinitionRecord(NamedTuple):
    """Binding of a variable at any given time."""

    name: str
    revision: int
    template_expr: str | Sentinel

    def __repr__(self) -> str:
        return f"VariableDefinitionRecord(name={self.name!r}, revision={self.revision}, expr={self.template_expr!r})"


class VariableValueRecord:
    """Binding of a variable at any given time."""

    def __init__(self, var_def: VariableDefinitionRecord, val_revision: int) -> None:
        self._var_def = var_def
        self._val_revision = val_revision

    @property
    def variable_definition(self) -> VariableDefinitionRecord:
        return self._var_def

    @property
    def value_revision(self) -> int:
        return self._val_revision

    @property
    def name(self) -> str:
        return self.variable_definition.name

    @property
    def revision(self) -> int:
        return self.variable_definition.revision

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(var_def={self.variable_definition!r}, val_revision={self.value_revision})"


class ConstantVariableValueRecord(VariableValueRecord):
    def __init__(self, var_def: VariableDefinitionRecord) -> None:
        super().__init__(var_def, 0)

    def copy(self) -> ConstantVariableValueRecord:
        return ConstantVariableValueRecord(self.variable_definition)


class ChangeableVariableValueRecord(VariableValueRecord):
    def __init__(
        self,
        variable_definition: VariableDefinitionRecord,
        value_revision: int,
        template_record: TemplateRecord,
    ) -> None:
        super().__init__(variable_definition, value_revision)
        self.template_record = template_record

    def copy(self) -> ChangeableVariableValueRecord:
        return ChangeableVariableValueRecord(
            self.variable_definition, self.value_revision, self.template_record
        )
