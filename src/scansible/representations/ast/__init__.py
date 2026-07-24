"""Abstract Syntax Tree (AST) representation of Ansible roles and playbooks.

The AST stays close to Ansible's own YAML syntax, but adds validation and
normalization into a typed, immutable tree to facilitate programmatic
reasoning on Ansible source code.

# Design decisions

## Pydantic-driven validation

Every AST node derives from `ASTEntity`, which itself derives from Pydantic's
`BaseModel`. AST nodes perform strict validation (i.e., `strict=True` and
`extra="forbid"`) so that invalid source code is rejected before it enters
further analysis. This validation is implemented with Pydantic and custom
validators (see below).

Nodes representing an entire file derive from `ASTFile`. Nodes appearing
within a file derive from `ASTNode`, and contain source `position`
information.

## Expressions and literals

Scalar and composite values (`Identifier`, `StrLiteral`, `IntLiteral`, ...,
`SeqLiteral`, `MapLiteral`) are deliberately *not* `ASTNode`/`BaseModel`
subclasses: they need to behave like the underlying Python type they wrap
(e.g. a `StrLiteral` must be usable as an actual `str`), which a Pydantic
`BaseModel` cannot also be. Instead, they implement the `Positioned`
protocol directly and supply a custom `__get_pydantic_core_schema__`, so
they can be used as ordinary field types while still carrying `position`
information (see `nodes/expression.py`).

`Expression` and `Condition`, by contrast, are `ASTNode` instances: they
eagerly parse their source string into a Jinja2 AST (`template`) at
validation time, alongside the original source (`raw`).

## Normalization

Ansible's YAML accepts many shorthand forms for the same value (e.g. a
single scalar where a list is expected, `None` handled equivalently to an
omitted directive, non-string scalars coerced to strings). These
field-level quirks are handled directly by the scalar/composite value
types themselves (`StrLiteral`, `SeqLiteral`, ...), see
`nodes/expression.py`. Reusable validation constraints are likewise
provided via custom type aliases in `_validators.py`.

Beyond field-level normalization, Ansible also has various shorthand and
legacy syntactical forms at the directive level, such as the many ways in
which modules and arguments can be specified, or the obsolete `sudo`/`su`
directives. Where possible, these are normalized into a canonical form
through bespoke `model_validator` and `field_validator` hooks.

## Extracting ASTs

This package provides two ways to extract ASTs:

1. Each `ASTFile` subclass (`TaskFile`, `VariableFile`, `Playbook`, ...)
   provides a `.load()` classmethod to construct an AST representation for
   the given file.
2. The `extract_role` and `extract_playbook` functions take a project path
   and create a root `AST` representation for the given role or playbook.

In both cases, extraction can be *lenient*, controlled by the `lenient`
argument to the `extract_*` functions, and the `lenient` attribute of
`ExtractionContext` given to the `.load()` classmethods. When extraction is
lenient, malformed input does not abort extraction and is instead skipped
and recorded in the `ExtractionContext`. Files that fail to parse are
logged in `broken_files`, whereas malformed entries within files (such as a
malformed task in a task list) are logged in `broken_tasks`.
"""

from __future__ import annotations

# Re-export public AST node types.
from .common import *
from .extractor import *
from .nodes import *

# Deliberate duplication as basedpyright otherwise complains about unsupported operations on `__all__`,
# possibly leading to degraded static tooling.
__all__ = [
    # .common
    "ExtractionContext",
    "BrokenTask",
    "BrokenFile",
    # .extractor
    "extract_playbook",
    "extract_role",
    # .nodes
    "AST",
    "ASTFile",
    "ASTNode",
    "Expression",
    "Condition",
    "Identifier",
    "StrLiteral",
    "IntLiteral",
    "FloatLiteral",
    "PercentLiteral",
    "BoolLiteral",
    "DateLiteral",
    "DatetimeLiteral",
    "SeqLiteral",
    "MapLiteral",
    "ScalarLiteral",
    "CompositeLiteral",
    "AnyLiteral",
    "AnyExpression",
    "VarsPrompt",
    "Play",
    "ImportPlaybook",
    "Playbook",
    "Role",
    "Platform",
    "RoleRequirement",
    "MetaBlock",
    "MetaFile",
    "LoopControl",
    "BaseTask",
    "Task",
    "Handler",
    "Block",
    "TaskFile",
    "HandlerFile",
    "VariableFile",
]
