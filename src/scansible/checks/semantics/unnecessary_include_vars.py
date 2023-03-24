from __future__ import annotations

from collections import defaultdict

from scansible.representations.pdg.extractor.context import VisibilityInformation
from scansible.representations.pdg.extractor.expressions import ScopeLevel
from scansible.representations.pdg.representation import (
    Def,
    Expression,
    Graph,
    Literal,
    Task,
    Variable,
)

from .base import Rule, RuleResult
from .utils import (
    find_variable_usages,
    get_def_conditions,
    get_def_expression,
    get_node_predecessors,
    get_nodes,
    get_used_variables,
)


def get_var_origin(graph: Graph, node: Variable) -> Expression | Literal | Task | None:
    def_tasks = get_node_predecessors(graph, node, node_type=Task, edge_type=Def)
    if def_tasks:
        # register, not set_fact. For register, it's possible for the variable
        # to have multiple DEFs (e.g. task itself and loop)
        return def_tasks[0]

    def_literal = get_node_predecessors(graph, node, node_type=Literal, edge_type=Def)
    if def_literal:
        assert (
            len(def_literal) == 1
        ), f"Expected {node!r} to be defined by one literal, found {len(def_literal)}"
        return def_literal[0]

    return get_def_expression(graph, node)


def is_idempotent_expr(graph: Graph, expr: Expression) -> bool:
    if not expr.idempotent:
        return False

    # Expression itself is idempotent, but perhaps its dependences aren't
    used_vars = get_used_variables(graph, expr)
    # Ignore dependences which themselves have been defined using set_fact or register,
    # even though their expression might be non-idempotent, the variable value itself isn't
    changeable_used_vars = [
        uv
        for uv in used_vars
        if uv.scope_level != ScopeLevel.SET_FACTS_REGISTERED.value
    ]
    # Find definitions of uses
    used_exprs: list[Expression] = [
        def_expr
        for used_node in changeable_used_vars
        if isinstance((def_expr := get_var_origin(graph, used_node)), Expression)
    ]

    if not used_exprs:
        return True

    return all(is_idempotent_expr(graph, d) for d in used_exprs)


class UnnecessaryIncludeVarsRule(Rule):
    def scan(self, graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
        included_vars = [
            node
            for node in get_nodes(graph, Variable)
            if node.scope_level == ScopeLevel.INCLUDE_VARS.value
        ]
        # Group into unique definitions so we only emit a warning for the first value version
        # We keep the other value versions so we can show all usages of this definition
        grouped_included_vars: dict[tuple[str, int], set[Variable]] = defaultdict(set)
        for v in included_vars:
            grouped_included_vars[(v.name, v.version)].add(v)

        results: list[RuleResult] = []
        for vs in grouped_included_vars.values():
            vs_sorted = sorted(vs, key=lambda v: v.version)
            v = vs_sorted[0]
            conditions = get_def_conditions(graph, v)

            if not conditions:
                warning_header = f'Unnecessary use of include_vars for variable "{v.name}@{v.version}"'
                warning_body_lines = [
                    f"Variable {v!r} is unconditionally included through include_vars.",
                    f"Variables included through include_vars have unusually high precedence, which makes tracing values difficult.",
                    f"Since this variable is unconditionally included, it can instead be placed into default variables, role variables, or a local scope, to prevent variable precedence issue.",
                    f"All usages of {v.name}@{v.version}:",
                ]
                for vval in vs_sorted:
                    warning_body_lines.extend(
                        f"\t{usage}" for usage in find_variable_usages(graph, vval)
                    )

                results.append(
                    RuleResult(
                        rule_category="Unnecessarily high precedence",
                        rule_name="Unnecessary include_vars",
                        rule_subname="",
                        rule_header=warning_header,
                        rule_message="\n".join(warning_body_lines),
                        role_name=graph.role_name,
                        role_version=graph.role_version,
                        location=v.location,
                    )
                )

        return results
