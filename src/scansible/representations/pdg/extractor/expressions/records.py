from __future__ import annotations

import dataclasses
from dataclasses import dataclass, field
from functools import partialmethod

from scansible.utils import Sentinel

from ... import representation as rep


@dataclass(frozen=True)
class _RecordBase:
    __replace__ = partialmethod(dataclasses.replace)


@dataclass(frozen=True)
class TemplateRecord(_RecordBase):
    """State of a template expression."""

    data_node: rep.DataNode
    expr_node: rep.Expression
    used_variables: list[tuple[str, int, int]]
    is_literal: bool = field(repr=False)

    @property
    def may_be_impure(self) -> bool:
        return not self.expr_node.is_pure

    def __repr__(self) -> str:
        return f"TemplateRecord(expr={self.expr_node.expr!r}, data_node={self.data_node.node_id}, expr_node={self.expr_node.node_id})"


@dataclass(frozen=True)
class VariableDefinitionRecord(_RecordBase):
    """Binding of a variable at any given time."""

    name: str
    revision: int
    template_expr: str | Sentinel


@dataclass(frozen=True)
class VariableValueRecord(_RecordBase):
    """Binding of a variable at any given time."""

    variable_definition: VariableDefinitionRecord
    value_revision: int

    @property
    def name(self) -> str:
        return self.variable_definition.name

    @property
    def revision(self) -> int:
        return self.variable_definition.revision


class ConstantVariableValueRecord(VariableValueRecord):
    def __init__(self, var_def: VariableDefinitionRecord) -> None:
        super().__init__(var_def, 0)

    def copy(self) -> ConstantVariableValueRecord:
        return ConstantVariableValueRecord(self.variable_definition)


@dataclass(frozen=True)
class ChangeableVariableValueRecord(VariableValueRecord):
    template_record: TemplateRecord

    def copy(self) -> ChangeableVariableValueRecord:
        return ChangeableVariableValueRecord(
            self.variable_definition, self.value_revision, self.template_record
        )
