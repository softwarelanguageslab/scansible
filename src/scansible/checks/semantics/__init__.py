from __future__ import annotations

from .base import TraversalRule as TraversalRule
from .unnecessary_include_vars import UnnecessaryIncludeVarsRule
from .unnecessary_set_fact import UnnecessarySetFactRule
from .unsafe_reuse_rule import UnsafeReuseRule
from .variable_shadowing_rule import VariableShadowingRule


def get_all_rules() -> list[TraversalRule]:
    return [
        UnsafeReuseRule(),
        UnnecessarySetFactRule(),
        UnnecessaryIncludeVarsRule(),
        VariableShadowingRule(),
    ]
