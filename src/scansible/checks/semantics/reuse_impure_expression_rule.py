from collections import defaultdict
from collections.abc import Collection, Iterable

from scansible.representations.pdg.extractor.context import \
    VisibilityInformation
from scansible.representations.pdg.representation import (Expression, Graph,
                                                          Variable)

from .base import Rule, RuleResult
from .utils import (ValueChangeReason, determine_value_version_change_reason,
                    find_variable_usages, get_nodes)


class ReuseImpureExpressionRule(Rule):
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
        # and check whether they had been re-evaluated following a non-idempotent expression.
        # (i.e. different value version) of one of their dependencies. We only
        # care about changes due to non-idempotency of direct dependences,
        # we'll check further issues downstream.
        nodes_sorted = sorted(nodes, key=lambda n: n.value_version)
        for v1, v2 in zip(nodes_sorted, nodes_sorted[1:]):
            (
                value_version_change_reason,
                value_change_context,
            ) = determine_value_version_change_reason(graph, v1, v2)
            if (
                value_version_change_reason
                != ValueChangeReason.EXPRESSION_NOT_IDEMPOTENT
            ):
                continue
            assert isinstance(
                value_change_context, Expression
            ), "Internal Error: Unexpected value change context type"

            warning_header = f'Potentially unsafe reuse of variable "{v2.name}@{v2.version}" due to potential non-idempotent expression.'
            warning_expl_lines = [
                f"This variable was previously used as {v1!r}, but now as {v2!r}.",
                f"The expression defining this variable has remained the same, however, it may not be idempotent.",
                f"Therefore, its value may have changed since the previous evaluation.",
                f"{value_change_context.expr!r} may be non-idempotent due to the usage of the following components:",
            ]
            for (
                non_idempotent_component
            ) in value_change_context.non_idempotent_components:
                warning_expl_lines.append(f" - {non_idempotent_component}")

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
                rule_name="Impure expression",
                rule_subname="",
                rule_header=warning_header,
                rule_message=warning_expl,
                role_name=graph.role_name,
                role_version=graph.role_version,
                location=v2.location,
            )
