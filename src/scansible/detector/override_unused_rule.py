from collections.abc import Collection, Iterable
from collections import defaultdict

from ..extractor.var_context import ScopeLevel
from ..extractor.context import VisibilityInformation
from ..models.graph import Graph
from ..models.nodes import Expression, IntermediateValue, Variable
from ..models.edges import Def
from .base import Rule, RuleResult
from .utils import get_nodes, get_def_expression, determine_value_version_change_reason, ValueChangeReason, find_variable_usages, get_all_used_variables, get_def_conditions, get_register_all_used_variables

class UnusedOverriddenRule(Rule):
    """Find variable definitions that are unusable because it's overridden by another definition at higher precedence.

    Only warns about variables that are defined AFTER the higher precedence alternative is defined, as those are missed
    by the other check. Variables defined BEFORE the higher precedence version are ignored here, as those are covered
    by the other check.
    """
    def scan(self, graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
        var_nodes = get_nodes(graph, Variable)

        # Grouping. We need the different values to find usages for reporting
        var_name_to_vars: dict[str, dict[int, list[Variable]]] = defaultdict(lambda: defaultdict(list))
        for node in var_nodes:
            var_value_list = var_name_to_vars[node.name][node.version]
            var_name_to_vars[node.name][node.version] = sorted(var_value_list + [node], key=lambda v: v.value_version)

        results: list[RuleResult] = []
        for name, related_nodes in var_name_to_vars.items():
            results.extend(self.scan_vars(graph, name, related_nodes, visinfo))
        return results

    def scan_vars(self, graph: Graph, name: str, nodes: dict[int, list[Variable]], visinfo: VisibilityInformation) -> Iterable[RuleResult]:
        # If there are no redefinitions, we don't need to check anything
        if len(nodes) <= 1:
            return

        nodes_sorted = sorted(nodes.items(), key=lambda n: n[0])
        for _, vals_v2_lst in nodes_sorted:
            v2 = vals_v2_lst[0]
            vals_v2 = set(vals_v2_lst)

            # Find the v2 which would conflict with this definition
            visibles = visinfo.get_info(v2.name, v2.version)
            for cand_name, cand_version in visibles:
                if cand_name != v2.name:
                    continue
                vals_v1_lst = nodes[cand_version]
                break
            else:
                # Doesn't conflict with anything with the same name
                continue

            v1 = vals_v1_lst[0]
            if v1.scope_level <= v2.scope_level:
                # Covered by other rule
                continue

            v2_ever_used = any(find_variable_usages(graph, v2_val) for v2_val in vals_v2)
            if v2_ever_used:
                # This can happen if v1 is an include parameter. It could happen
                # that the included file includes a variable/sets a fact with
                # the same name as a parameter. This new variable can be used
                # when the included file is left. Example: jkupferer.openshift_aws_cleanup
                assert v1.scope_level == ScopeLevel.INCLUDE_PARAMS.value, f'Determined that variable {v2!r} should be unusable because it is shadowed by a higher precedence one, but there appear to be usages either way'
                continue

            warning_header = f'Unused variable "{name}@{v2.version}" because it is already defined at higher precedence.'
            warning_expl_lines = [
                f'Variable {v2!r}, defined in {v2.location!r}, is never used because it is shadowed by {v1!r}, defined in {v1.location!r}, which takes precedence.',
            ]

            yield RuleResult(
                    rule_category='Unintended override',
                    rule_name='Unused because shadowed',
                    rule_subname='',
                    rule_header=warning_header,
                    rule_message='\n'.join(warning_expl_lines),
                    role_name=graph.role_name,
                    role_version=graph.role_version,
                    location=v2.location)
