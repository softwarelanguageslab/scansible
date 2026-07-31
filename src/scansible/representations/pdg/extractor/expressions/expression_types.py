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
from __future__ import annotations

from scansible.representations import ast
from scansible.representations.pdg.representation import ValidTypeStr

_AST_TYPE_NAME_TO_BUILTIN_NAME: dict[str, ValidTypeStr] = {
    # FIXME: this can likely be parsed better
    "IntLiteral": "int",
    "StrLiteral": "str",
    "SeqLiteral": "list",
    "MapLiteral": "dict",
    "FloatLiteral": "float",
    "BoolLiteral": "bool",
    "DateLiteral": "date",
    "DatetimeLiteral": "datetime",
    "NoneType": "NoneType",
}


def extract_type_name(value: ast.AnyExpression) -> ValidTypeStr:
    if isinstance(value, ast.StrLiteral) and value.is_vaulted:
        return "VaultValue"
    type_ = value.__class__.__name__
    return _AST_TYPE_NAME_TO_BUILTIN_NAME[type_]
