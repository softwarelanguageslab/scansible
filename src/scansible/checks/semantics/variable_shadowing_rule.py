from __future__ import annotations

from typing import final, override

from collections import defaultdict
from collections.abc import Iterable

from scansible.pdg.builder.semantics import EnvironmentType
from scansible.pdg.representation import Graph, Variable

from ..base import Finding
from .base import TraversalRule
from .utils import (
    get_all_used_variables,
    get_def_conditions,
    get_def_expression,
    get_register_all_used_variables,
)


def _find_shadowing_pairs(
    var_nodes: Iterable[Variable],
) -> Iterable[tuple[str, list[Variable], list[Variable]]]:
    """Return pairs of shadowed and shadowing variable values, alongside the variable name."""
    var_name_to_vars: dict[str, dict[int, list[Variable]]] = defaultdict(
        lambda: defaultdict(list)
    )
    for node in var_nodes:
        var_value_list = var_name_to_vars[node.name][node.version]
        var_name_to_vars[node.name][node.version] = sorted(
            var_value_list + [node], key=lambda v: v.value_version
        )

    for name, nodes in var_name_to_vars.items():
        # If there are no redefinitions, there's nothing to compare
        if len(nodes) <= 1:
            continue

        nodes_sorted = sorted(nodes.items(), key=lambda n: n[0])
        for _, vals_next_lst in nodes_sorted:
            next_ = vals_next_lst[0]

            # Find the definition that was visible before this one, if any.
            # Not necessarily the one it's shadowed by, that depends on their precendence.
            vals_prior_lst = (
                nodes.get(next_.prior_version)
                if next_.prior_version is not None
                else None
            )
            if vals_prior_lst is None:
                continue

            prior = vals_prior_lst[0]
            if prior.scope_level > next_.scope_level:
                yield name, vals_prior_lst, vals_next_lst
            else:
                yield name, vals_next_lst, vals_prior_lst


@final
class VariableShadowingRule(TraversalRule):
    """Find variable definitions that unconditionally shadow an earlier definition of the same variable.

    Of a pair of definitions of the same variable, whichever one actually takes precedence at runtime
    (the higher, or equal, scope level) is the one that shadows the other. This is flagged when it looks
    unintentional: the shadowing definition's initialiser and conditions never reference the shadowed one,
    and both are defined under unrelated conditions.
    """

    code = "SEM004"

    @override
    def detect(self, graph: Graph) -> list[Finding]:
        results: list[Finding] = []
        for name, shadowing, shadowed in _find_shadowing_pairs(
            graph.get_nodes(Variable)
        ):
            results.extend(self._check(graph, name, shadowing, shadowed))
        return results

    def _check(
        self,
        graph: Graph,
        name: str,
        shadowing_lst: list[Variable],
        shadowed_lst: list[Variable],
    ) -> Iterable[Finding]:
        shadowing = shadowing_lst[0]
        shadowed = shadowed_lst[0]

        if shadowed.scope_level == EnvironmentType.UNDEFINED.value:
            # Cannot shadow an undefined variable.
            return

        vals_shadowed = set(shadowed_lst)
        shadowing_expr = get_def_expression(graph, shadowing)

        if shadowing_expr is not None:
            # Check whether the shadowed definition is used in the shadowing one's
            # initialiser. If it is, the shadowing isn't unconditional
            uses = get_all_used_variables(graph, shadowing_expr)
            if vals_shadowed & set(uses):
                return
        elif shadowing.scope_level == EnvironmentType.SET_FACTS_REGISTERED.value:
            # For variables defined through register, we instead check all
            # variables used in the task evaluation
            uses = get_register_all_used_variables(graph, shadowing)
            if vals_shadowed & set(uses):
                return

        all_cond_uses_shadowed = {
            cu1  # pyright: ignore[reportUnhashable]
            for cond in get_def_conditions(graph, shadowed)
            for cu1 in get_all_used_variables(graph, cond)
        }
        all_cond_uses_shadowing = {
            cu2  # pyright: ignore[reportUnhashable]
            for cond in get_def_conditions(graph, shadowing)
            for cu2 in get_all_used_variables(graph, cond)
        }

        # Perhaps the shadowed definition shows up in the shadowing one's condition?
        if all_cond_uses_shadowing & vals_shadowed:
            return

        # Last resort: If the shadowed definition is conditional, check whether they
        # use the same variables
        if all_cond_uses_shadowed & all_cond_uses_shadowing:
            return

        summary = f"Variable `{name}@{shadowing.version}` unconditionally shadows a previous definition"
        explanation = (
            f"{shadowing!r} shadows the previous definition {shadowed!r}. "
            f"Neither its initialiser nor its conditions reference {shadowed!r}, "
            "and both are defined under unrelated conditions."
        )

        yield Finding(
            code=self.code,
            summary=summary,
            explanation=explanation,
            location=shadowing.location,
            hint_location=shadowed.location,
            hint_text="shadowed definition here",
        )
