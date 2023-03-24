from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from scansible.representations.pdg.extractor.context import VisibilityInformation
from scansible.representations.pdg.extractor.expressions import EnvironmentType
from scansible.representations.pdg.representation import Graph, Variable

from .base import Rule, RuleResult
from .utils import (
    find_variable_usages,
    get_all_used_variables,
    get_def_conditions,
    get_def_expression,
    get_nodes,
    get_register_all_used_variables,
    is_registered_variable,
    register_task_has_conditions,
)


class UnconditionalOverrideRule(Rule):
    """Find variable definitions that unconditionally override a previous definition of the same variable.

    Unconditional here means that the value of the original definition is not used in the new definition, either
    through the initialiser or (more commonly) the condition used to define the variable. If both variable definitions
    are conditionally defined, we consider the override unconditionally if the second version uses a completely different
    condition. That analysis is fairly naive, we merely check whether the conditions have any variable usage in common.
    """

    def scan(self, graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
        var_nodes = get_nodes(graph, Variable)

        # Grouping. We need the different values to find usages for reporting
        var_name_to_vars: dict[str, dict[int, list[Variable]]] = defaultdict(
            lambda: defaultdict(list)
        )
        for node in var_nodes:
            var_value_list = var_name_to_vars[node.name][node.version]
            var_name_to_vars[node.name][node.version] = sorted(
                var_value_list + [node], key=lambda v: v.value_version
            )

        results: list[RuleResult] = []
        for name, related_nodes in var_name_to_vars.items():
            results.extend(self.scan_vars(graph, name, related_nodes, visinfo))
        return results

    def scan_vars(
        self,
        graph: Graph,
        name: str,
        nodes: dict[int, list[Variable]],
        visinfo: VisibilityInformation,
    ) -> Iterable[RuleResult]:
        # If there are no redefinitions, we don't need to check anything
        if len(nodes) <= 1:
            return

        nodes_sorted = sorted(nodes.items(), key=lambda n: n[0])
        for _, vals_v2_lst in nodes_sorted:
            v2 = vals_v2_lst[0]

            # Find the v2 which would be overridden by this definition
            visibles = visinfo.get_info(v2.name, v2.version)
            for cand_name, cand_version in visibles:
                if cand_name != v2.name:
                    continue
                vals_v1_lst = nodes[cand_version]
                break
            else:
                # Doesn't override anything with the same name
                continue

            v1 = vals_v1_lst[0]
            if v1.scope_level > v2.scope_level:
                # v2 cannot override v1 as v1 has higher precedence, nothing to check here
                # We have a separate check for variables defined when a higher-precedence alternative is in scope.
                continue
            if v1.scope_level == 0 or v2.scope_level == 0:
                # v1 or v2 are undefined, so skip this
                continue

            vals_v1 = set(vals_v1_lst)

            e2 = get_def_expression(graph, v2)

            if e2 is not None:
                # Check whether any v1 is used in initialiser of v2. If it is,
                # it isn't an unconditional override
                e2_uses = get_all_used_variables(graph, e2)
                if vals_v1 & set(e2_uses):
                    continue
            elif v2.scope_level == EnvironmentType.SET_FACTS_REGISTERED.value:
                # For variables defined through register, we instead check all
                # variables used in the task evaluation
                e2_uses = get_register_all_used_variables(graph, v2)
                if vals_v1 & set(e2_uses):
                    continue

            all_cond_uses_v1 = set(
                cu1
                for cond_v1 in get_def_conditions(graph, v1)
                for cu1 in get_all_used_variables(graph, cond_v1)
            )
            all_cond_uses_v2 = set(
                cu2
                for cond_v2 in get_def_conditions(graph, v2)
                for cu2 in get_all_used_variables(graph, cond_v2)
            )

            # Perhaps v1 shows up in the condition of v2?
            if all_cond_uses_v2 & vals_v1:
                continue

            # Last resort: If v1 is conditionally defined, check whether they use the same variables
            if all_cond_uses_v1 & all_cond_uses_v2:
                continue

            v1_ever_used = any(
                find_variable_usages(graph, v1_val) for v1_val in vals_v1
            )
            is_due_to_register = is_registered_variable(
                graph, v2
            ) and register_task_has_conditions(graph, v2)

            warning_header = f'Potential unintended unconditional override of variable "{name}@{v2.version}".'
            warning_expl_lines = [
                f"Variable {v2!r}, defined in {v2.location!r}, unconditionally overrides a previous definition of {name!r}.",
                f"{name!r} was previously defined as {v1!r} in {v1.location!r}.",
                f"Neither the initialiser of {v2!r} nor its conditions reference {v1!r}, and both are defined under unrelated conditions.",
            ]
            if not v1_ever_used:
                warning_expl_lines.append(
                    "Due to this override, the original definition is never used."
                )
            if is_due_to_register:
                warning_expl_lines.append(
                    f"{v2!r} is defined through `register` on a conditionally executed task. However, even when this task is skipped, the variable is still defined."
                )
            if e2 is not None:
                warning_expl_lines.append(f"Initialiser of {v2!r}: {e2.expr!r}")
            if all_cond_uses_v1:
                vstr = ", ".join(uv1.name for uv1 in all_cond_uses_v1)
                warning_expl_lines.append(
                    f"Variables used in conditional definition of original definition ({v1!r}): {vstr}"
                )
            if all_cond_uses_v2:
                vstr = ", ".join(uv2.name for uv2 in all_cond_uses_v2)
                warning_expl_lines.append(
                    f"Variables used in conditional definition of new definition ({v2!r}): {vstr}"
                )

            rule_subname = ""
            if is_due_to_register:
                rule_subname += "Due to register"
            if not v1_ever_used:
                rule_subname += "original unused"
            yield RuleResult(
                rule_category="Unintended override",
                rule_name="Unconditional override",
                rule_subname=rule_subname,
                rule_header=warning_header,
                rule_message="\n".join(warning_expl_lines),
                role_name=graph.role_name,
                role_version=graph.role_version,
                location=v2.location,
            )
