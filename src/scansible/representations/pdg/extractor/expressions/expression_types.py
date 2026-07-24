"""Expression types.

Some notes on terminology:
- **Expressions** are any construct that produces a value.
- **Templated expressions** are expressions that contain Jinja2 template constructions (`{{ }}` or `{% %}`).
- **Scalar literals** are simple literal expressions representing scalar datatypes (str, int, float, bool, None, and date).
- **Composite expressions** are expressions that represent composite data structures (list, dict, set, tuple, ...).
  They consist of other expressions, which in turn can in turn be composites, templated expressions, or scalars.
- **Conditions** are special-case templated expressions without Jinja2 delimiters, used in certain playbook keywords
  where conditions are expected (e.g., a task's `when` keyword).
"""

# FIXME: Terminology above needs to be applied consistently in the rest of the project, e.g., in the PDG node types.
# FIXME: AST parser should use explicit types to distinguish these types of expressions, rather than making every expression
#        correspond to its YAML datatype, as this confounds scalar strings, expressions, and conditions. Also a concrete type
#        for scalar literals instead of raw data types. This distinction will allow us to do type-based dispatching here.
#        It could also eagerly parse expressions.

from __future__ import annotations

from typing import NamedTuple, TypeGuard, cast

from collections.abc import Mapping, Sequence

from ansible.parsing.dataloader import DataLoader
from ansible.template import Templar

from scansible.representations import ast
from scansible.representations.pdg.extractor.expressions.records import TemplatableType
from scansible.representations.pdg.representation import ValidTypeStr
from scansible.types import AnyValue, ScalarValue


class ScalarLiteral(NamedTuple):
    type: ValidTypeStr
    value: ScalarValue


class SequenceExpression(NamedTuple):
    type: ValidTypeStr  # concrete sequence type
    elements: Sequence[Expression]


class MappingExpression(NamedTuple):
    type: ValidTypeStr  # concrete sequence type
    mapping: Mapping[Expression, Expression]


# FIXME: Cannot wrap as str subclass as Ansible positioning location is lost.
class TemplatedExpression(NamedTuple):
    raw: str


class Condition(NamedTuple):
    raw: str


CompositeExpression = SequenceExpression | MappingExpression


Expression = (
    ScalarLiteral
    | MappingExpression
    | SequenceExpression
    | Condition
    | TemplatedExpression
)


_ANSIBLE_TYPE_NAME_TO_BUILTIN_NAME: dict[str, ValidTypeStr] = {
    "AnsibleUnicode": "str",
    "AnsibleSequence": "list",
    "AnsibleMapping": "dict",
    "AnsibleUnsafeText": "str",
    "FrozenDict": "dict",
    "tuple": "list",
    # FIXME this can likely be parsed better, and the above shouldn't occur anymore
    "IntLiteral": "int",
    "StrLiteral": "str",
    "SeqLiteral": "list",
    "MapLiteral": "dict",
    "FloatLiteral": "float",
    "BoolLiteral": "bool",
    "DateLiteral": "date",
    "DatetimeLiteral": "datetime",
}


def extract_type_name(value: AnyValue) -> ValidTypeStr:
    type_ = value.__class__.__name__
    return _ANSIBLE_TYPE_NAME_TO_BUILTIN_NAME.get(type_, cast(ValidTypeStr, type_))


def is_template(expr: AnyValue) -> TypeGuard[TemplatableType]:
    templar = Templar(DataLoader())
    return templar.is_template(expr)


# TODO: The wrapping functions below should also parse the expression ASTs.
#       In the current var_context implementation, this is difficult as the
#       condition parsing depends on the current environment, this should be
#       properly addressed by representing the indirection in the graph correctly.


def wrap_expression(expr: AnyValue) -> Expression:
    if isinstance(expr, ast.Expression):
        expr = expr.raw

    type_name = extract_type_name(expr)

    if isinstance(expr, Sequence) and not isinstance(expr, str):
        return SequenceExpression(
            type_name, [wrap_expression(element) for element in expr]
        )
    elif isinstance(expr, Mapping):
        return MappingExpression(
            type_name,
            {wrap_expression(k): wrap_expression(v) for k, v in expr.items()},
        )
    elif not is_template(expr):
        return ScalarLiteral(type_name, expr)
    else:
        assert isinstance(expr, str)
        return TemplatedExpression(expr)


def wrap_condition(expr: AnyValue) -> Expression:
    if isinstance(expr, str):
        return Condition(expr)
    if isinstance(expr, ast.Condition):
        return Condition(expr.raw)
    else:
        return wrap_expression(expr)
