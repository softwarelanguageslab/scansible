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

## Normalization

Ansible's YAML accepts many shorthand forms for the same value (e.g. a
single string where a list is expected, `None` handled equivalently to an
omitted directive, non-string scalars coerced to strings). Field-level
quirks like these are normalized through reusable normalization markers
attached to fields via `Annotated` metadata, see `_normalizers.py`.
Reusable validation constraints are likewise provided via custom type
aliases in `_validators.py`.

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

# FIXME!!! Source code position information is largely broken due to Pydantic coercing Ansible types (AnsibleUnicode, AnsibleMapping, ...)
# to plain data types (str, dict, ...), losing the custom `ansible_pos` field.

from __future__ import annotations

# Re-export public AST node types.
from . import extractor as extractor
from .common import BrokenFile as BrokenFile
from .common import BrokenTask as BrokenTask
from .common import ExtractionContext as ExtractionContext
from .common import Position as Position
from .extractor import extract_playbook as extract_playbook
from .extractor import extract_role as extract_role
from .nodes import AST as AST
from .nodes import ASTFile as ASTFile
from .nodes import ASTNode as ASTNode
from .nodes import BaseTask as BaseTask
from .nodes import Block as Block
from .nodes import Handler as Handler
from .nodes import HandlerFile as HandlerFile
from .nodes import LoopControl as LoopControl
from .nodes import MetaBlock as MetaBlock
from .nodes import MetaFile as MetaFile
from .nodes import Platform as Platform
from .nodes import Play as Play
from .nodes import Playbook as Playbook
from .nodes import Role as Role
from .nodes import RoleRequirement as RoleRequirement
from .nodes import Task as Task
from .nodes import TaskFile as TaskFile
from .nodes import VariableFile as VariableFile
from .nodes import VarsPrompt as VarsPrompt
