from __future__ import annotations

from collections import defaultdict
from collections.abc import Collection, Iterable

from scansible.representations.pdg.extractor.context import VisibilityInformation
from scansible.representations.pdg.representation import Graph, Variable

from .base import Rule, RuleResult
from .utils import (
    ValueChangeReason,
    determine_value_version_change_reason,
    find_variable_usages,
    get_nodes,
)


class ReuseChangedVariableRule(Rule):
    def scan(self, graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
        var_nodes = get_nodes(graph, Variable)

        # Mapping from (variable name, definition version) to all variables in graph with those properties.
        # I.e. aggregation of all nodes of the same variable but with different values
        var_name_to_vars: dict[tuple[str, int], set[Variable]] = defaultdict(set)
        for node in var_nodes:
            var_name_to_vars[(node.name, node.version)].add(node)

        results: list[RuleResult] = []
        for related_nodes in var_name_to_vars.values():
            results.extend(self.scan_vars(graph, related_nodes))
        return results

    def scan_vars(
        self, graph: Graph, nodes: Collection[Variable]
    ) -> Iterable[RuleResult]:
        assert len({node.value_version for node in nodes}) == len(
            nodes
        ), "Somehow different nodes with same value version?!"
        # If there's only one value for this variable version, we don't need to
        # check anything.
        if len(nodes) <= 1:
            return

        # Sort the nodes so we can check each pair of (prev_value, next_value) individually.
        # In the following, for each of these pairs, we check their expressions
        # and check whether they had been re-evaluated following a redefinition
        # (i.e. different version, not different value version) of one of their
        # dependencies. We don't care about new value versions due to redefinitions
        # because of an upstream new value version. These occur under two circumstances:
        # non-idempotent expressions (different check), and a cascade of a redefinition
        # upstream. We ignore the latter, as we'll analyse the impact of a redefinition
        # upstream, not here.
        nodes_sorted = sorted(nodes, key=lambda n: n.value_version)
        for v1, v2 in zip(nodes_sorted, nodes_sorted[1:]):
            (
                value_version_change_reason,
                value_change_context,
            ) = determine_value_version_change_reason(graph, v1, v2)
            if value_version_change_reason != ValueChangeReason.DEPENDENCY_REDEFINED:
                continue
            assert (
                isinstance(value_change_context, tuple)
                and len(value_change_context) == 2
            ), "Internal Error: Unexpected value change context type"

            dep_v1, dep_v2 = value_change_context

            warning_header = f'Potentially unsafe reuse of variable "{v2.name}@{v2.version}" due to potential change in dependence.'
            warning_expl_lines = [
                f"This variable was previously used as {v1!r}, but now as {v2!r}.",
                f"The expression defining this variable has remained the same, however, it references a variable {dep_v1.name!r}.",
                f"This dependence has potentially been changed since the previous usage.",
                f"In the first usages of {v1.name!r}, {dep_v1.name!r} was defined in {dep_v1.location!r}",
                f"In later usages of {v2.name!r}, {dep_v1.name!r} was defined in {dep_v2.location!r}",
            ]
            warning_expl_lines.append(f"All usages of {v1!r}:")
            warning_expl_lines.extend(
                f"\t{usage}" for usage in find_variable_usages(graph, v1)
            )
            warning_expl_lines.append(f"All usages of {v2!r}:")
            warning_expl_lines.extend(
                f"\t{usage}" for usage in find_variable_usages(graph, v2)
            )
            warning_expl = "\n".join(warning_expl_lines)

            yield RuleResult(
                rule_category="Unsafe reuse",
                rule_name="Redefined dependence",
                rule_subname="",
                rule_header=warning_header,
                rule_message=warning_expl,
                role_name=graph.role_name,
                role_version=graph.role_version,
                location=v2.location,
            )
