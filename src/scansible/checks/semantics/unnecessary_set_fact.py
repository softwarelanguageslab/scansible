from __future__ import annotations

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


class UnnecessarySetFactRule(Rule):
    def scan(self, graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
        set_facted_vars = [
            node
            for node in get_nodes(graph, Variable)
            if node.scope_level == ScopeLevel.SET_FACTS_REGISTERED.value
        ]

        results: list[RuleResult] = []
        for v in set_facted_vars:
            vorigin = get_var_origin(graph, v)
            assert (
                vorigin is not None
            ), f"Internal Error: {v!r} was defined with set_fact but has no definition"

            if isinstance(vorigin, Task):
                # register, not set_fact
                continue

            is_idempotent_def = isinstance(vorigin, Literal) or is_idempotent_expr(
                graph, vorigin
            )
            conditions = get_def_conditions(graph, v)
            is_idempotent_condition = (not conditions) or all(
                is_idempotent_expr(graph, cond) for cond in conditions
            )

            if is_idempotent_def and is_idempotent_condition:
                warning_header = (
                    f'Unnecessary use of set_fact for variable "{v.name}@{v.version}"'
                )
                warning_body_lines: list[str] = []

                if isinstance(vorigin, Literal):
                    warning_body_lines.append(
                        f"Variable {v!r} is defined by the literal `{vorigin.value}`"
                    )
                else:
                    warning_body_lines.append(
                        f"Variable {v!r} is defined the expression `{vorigin.expr}`"
                    )
                warning_body_lines.append("This initialiser is fully idempotent.")
                if conditions:
                    warning_body_lines.append(
                        "Moreover, all conditionals for this variable are idempotent:"
                    )
                    warning_body_lines.extend(
                        [f" - `{condition.expr}`" for condition in conditions]
                    )
                warning_body_lines.append(
                    "Therefore, greedily evaluating this initialiser serves no specific purpose and identical results can likely be achieved at lower precedence."
                )
                results.append(
                    RuleResult(
                        rule_category="Unnecessarily high precedence",
                        rule_name="Unnecessary set_fact",
                        rule_subname="",
                        rule_header=warning_header,
                        rule_message="\n".join(warning_body_lines),
                        role_name=graph.role_name,
                        role_version=graph.role_version,
                        location=v.location,
                    )
                )

        return results
