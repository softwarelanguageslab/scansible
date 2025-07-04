from __future__ import annotations

from scansible.representations.pdg.extractor.context import VisibilityInformation
from scansible.representations.pdg.extractor.expressions import EnvironmentType
from scansible.representations.pdg.representation import (
    Def,
    Expression,
    Graph,
    Literal,
    Task,
    Variable,
)

from .base import Rule, RuleResult
from .utils import get_def_conditions, get_def_expression, get_used_variables


def get_var_origin(graph: Graph, node: Variable) -> Expression | Literal | Task | None:
    def_tasks = graph.get_predecessors(node, node_type=Task, edge_type=Def)
    if def_tasks:
        # register, not set_fact. For register, it's possible for the variable
        # to have multiple DEFs (e.g. task itself and loop)
        return def_tasks[0]

    def_literal = graph.get_predecessors(node, node_type=Literal, edge_type=Def)
    if def_literal:
        assert len(def_literal) == 1, (
            f"Expected {node!r} to be defined by one literal, found {len(def_literal)}"
        )
        return def_literal[0]

    return get_def_expression(graph, node)


def is_pure_expr(graph: Graph, expr: Expression) -> bool:
    if not expr.is_pure:
        return False

    # Expression itself is pure, but perhaps its dependences aren't
    used_vars = get_used_variables(graph, expr)
    # Ignore dependences which themselves have been defined using set_fact or register,
    # even though their expression might be impure, the variable value itself isn't
    changeable_used_vars = [
        uv
        for uv in used_vars
        if uv.scope_level != EnvironmentType.SET_FACTS_REGISTERED.value
    ]
    # Find definitions of uses
    used_exprs: list[Expression] = [
        def_expr
        for used_node in changeable_used_vars
        if isinstance((def_expr := get_var_origin(graph, used_node)), Expression)
    ]

    if not used_exprs:
        return True

    return all(is_pure_expr(graph, d) for d in used_exprs)


class UnnecessarySetFactRule(Rule):
    def scan(self, graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
        set_facted_vars = [
            node
            for node in graph.get_nodes(Variable)
            if node.scope_level == EnvironmentType.SET_FACTS_REGISTERED.value
        ]

        results: list[RuleResult] = []
        for v in set_facted_vars:
            vorigin = get_var_origin(graph, v)
            assert vorigin is not None, (
                f"Internal Error: {v!r} was defined with set_fact but has no definition"
            )

            if isinstance(vorigin, Task):
                # register, not set_fact
                continue

            is_pure_def = isinstance(vorigin, Literal) or is_pure_expr(graph, vorigin)
            conditions = get_def_conditions(graph, v)
            is_pure_condition = (not conditions) or all(
                is_pure_expr(graph, cond) for cond in conditions
            )

            if is_pure_def and is_pure_condition:
                warning_header = (
                    f'Unnecessary use of set_fact for variable "{v.name}@{v.version}"'
                )
                warning_body_lines: list[str] = []

                if isinstance(vorigin, Literal):
                    warning_body_lines.append(f"Variable {v!r} is defined by a literal")
                else:
                    warning_body_lines.append(
                        f"Variable {v!r} is defined the expression `{vorigin.expr}`"
                    )
                warning_body_lines.append("This initialiser is fully pure.")
                if conditions:
                    warning_body_lines.append(
                        "Moreover, all conditionals for this variable are pure:"
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
