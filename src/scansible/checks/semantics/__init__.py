from __future__ import annotations

from typing import TYPE_CHECKING

from .unnecessary_include_vars import UnnecessaryIncludeVarsRule
from .unnecessary_set_fact import UnnecessarySetFactRule
from .unsafe_reuse_rule import UnsafeReuseRule
from .variable_shadowing_rule import VariableShadowingRule

if TYPE_CHECKING:
    from .base import TraversalRule as TraversalRule


def get_all_rules() -> list[TraversalRule]:
    return [
        UnsafeReuseRule(),
        UnnecessarySetFactRule(),
        UnnecessaryIncludeVarsRule(),
        VariableShadowingRule(),
    ]
