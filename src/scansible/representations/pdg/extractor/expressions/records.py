from __future__ import annotations

from typing import TYPE_CHECKING

import dataclasses
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from functools import partialmethod

from scansible.representations import structural as struct
from scansible.utils import Sentinel

from ... import representation as rep

if TYPE_CHECKING:
    from .environments import EnvironmentType

TemplatableType = (
    str | Mapping["struct.Scalar", "struct.AnyValue"] | Sequence["struct.AnyValue"]
)


@dataclass(frozen=True)
class _RecordBase:
    __replace__ = partialmethod(dataclasses.replace)


class TemplateRecord(_RecordBase):
    """Result of a template expression evaluation."""

    data_node: rep.DataNode
    used_variables: list[VariableValueRecord]

    @property
    def may_be_impure(self) -> bool:
        ...

    @property
    def is_literal(self) -> bool:
        ...


@dataclass(frozen=True)
class LiteralEvaluationResult(TemplateRecord):
    """Result of a literal expression."""

    data_node: rep.DataNode
    used_variables: list[VariableValueRecord] = field(
        init=False, default_factory=list, repr=False
    )

    @property
    def is_literal(self) -> bool:
        return True

    @property
    def may_be_impure(self) -> bool:
        return False


@dataclass(frozen=True)
class TemplateEvaluationResult(TemplateRecord):
    """Result of a template expression evaluation."""

    data_node: rep.DataNode
    expr_node: rep.Expression | rep.CompositeLiteral
    used_variables: list[VariableValueRecord]

    @property
    def is_literal(self) -> bool:
        return False

    @property
    def may_be_impure(self) -> bool:
        return isinstance(self.expr_node, rep.Expression) and not self.expr_node.is_pure


@dataclass(frozen=True)
class VariableDefinitionRecord(_RecordBase):
    """Binding of a variable at any given time."""

    name: str
    revision: int
    initialiser: struct.AnyValue | Sentinel
    eagerly_evaluated: bool
    env_type: EnvironmentType


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
