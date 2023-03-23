from __future__ import annotations

from scansible.representations.pdg import Graph
from scansible.representations.pdg.extractor.context import VisibilityInformation

from .base import RuleResult
from .override_unused_rule import UnusedOverriddenRule
from .reuse_changed_rule import ReuseChangedVariableRule
from .reuse_impure_expression_rule import ReuseImpureExpressionRule
from .unconditional_override_rule import UnconditionalOverrideRule
from .unnecessary_include_vars import UnnecessaryIncludeVarsRule
from .unnecessary_set_fact import UnnecessarySetFactRule

ALL_RULES = [
    ReuseImpureExpressionRule(),
    ReuseChangedVariableRule(),
    UnnecessarySetFactRule(),
    UnnecessaryIncludeVarsRule(),
    UnconditionalOverrideRule(),
    UnusedOverriddenRule(),
    # SanityCheckNumberOfTasksRule(),
]


def run_all_checks(graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
    return [res for rule in ALL_RULES for res in rule.scan(graph, visinfo)]
