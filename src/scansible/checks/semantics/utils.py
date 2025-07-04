from __future__ import annotations

from enum import Enum

from scansible.representations.pdg.extractor.expressions import EnvironmentType
from scansible.representations.pdg.representation import (
    ControlNode,
    DataFlowEdge,
    Def,
    Expression,
    Graph,
    IntermediateValue,
    Literal,
    Task,
    Use,
    Variable,
    When,
)


def get_def_expression(
    graph: Graph, node: Variable | IntermediateValue
) -> Expression | None:
    if isinstance(node, IntermediateValue):
        def_iv = node
    else:
        # Need to follow intermediate value first
        pred_ivs = graph.get_predecessors(
            node, node_type=IntermediateValue, edge_type=Def
        )
        num_pred_ivs = len(pred_ivs)
        num_succ_ivs = len(graph.get_successors(node, node_type=IntermediateValue))
        assert num_succ_ivs <= 1, (
            f"Expected {node!r} to define at most one intermediate value, but found {num_succ_ivs}"
        )
        assert num_pred_ivs <= 1, (
            f"Expected {node!r} to be defined by at most one intermediate value, but found {num_pred_ivs}"
        )

        if not pred_ivs:
            # No defining expression, maybe this variable is supplied by the client of a role
            # or this variable is the result of a register keyword
            return None

        def_iv = pred_ivs[0]

    def_exprs = graph.get_predecessors(def_iv, node_type=Expression, edge_type=Def)
    num_def_exprs = len(def_exprs)
    assert num_def_exprs == 1, (
        f"Expected intermediate value defining {def_iv!r} to be defined by exactly one expression, but found {num_def_exprs}"
    )
    return def_exprs[0]


def get_def_conditions(graph: Graph, v: Variable) -> list[Expression]:
    conditional_data_nodes = graph.get_predecessors(v, edge_type=When)

    cond_exprs: list[Expression] = []
    for civ in conditional_data_nodes:
        if isinstance(civ, Literal):
            continue
        assert isinstance(civ, IntermediateValue), (
            f"Internal Error: Expected {v!r} to be conditionally defined by literal or intermediate value, found {civ!r}"
        )
        expr = get_def_expression(graph, civ)
        assert isinstance(expr, Expression), (
            f"Internal Error: {v!r} is conditionally defined without condition expression"
        )
        cond_exprs.append(expr)

    return cond_exprs


def get_used_variables(graph: Graph, expr: Expression) -> list[Variable]:
    usages = graph.get_predecessors(expr, edge_type=Use)
    usages_cleaned: list[Variable] = []
    for usage in usages:
        assert isinstance(usage, Variable), (
            f"Internal Error: Expression {expr!r} uses a non-variable: {usage!r}"
        )
        usages_cleaned.append(usage)
    return usages_cleaned


def get_all_used_variables(graph: Graph, expr: Expression) -> list[Variable]:
    """Like above, but include transitive usages."""
    direct_usages = get_used_variables(graph, expr)
    indirect_expressions = [
        trans_expr
        for du in direct_usages
        if (trans_expr := get_def_expression(graph, du)) is not None
    ]

    indirect_usages = [
        trans_usage
        for trans_expr in indirect_expressions
        for trans_usage in get_all_used_variables(graph, trans_expr)
    ]
    return direct_usages + indirect_usages


def get_register_all_used_variables(graph: Graph, var: Variable) -> list[Variable]:
    """Like above, but for variables defined through register."""
    def_nodes = graph.get_predecessors(var, node_type=ControlNode, edge_type=Def)
    usages: list[Variable] = []

    for def_node in def_nodes:
        used_ivs = graph.get_predecessors(
            def_node, node_type=IntermediateValue, edge_type=Use
        )
        for used_iv in used_ivs:
            expr = get_def_expression(graph, used_iv)
            assert expr is not None
            usages.extend(get_used_variables(graph, expr))

    return usages


def is_registered_variable(graph: Graph, var: Variable) -> bool:
    return var.scope_level == EnvironmentType.SET_FACTS_REGISTERED.value and bool(
        graph.get_predecessors(var, node_type=Task, edge_type=Def)
    )


def register_task_has_conditions(graph: Graph, var: Variable) -> bool:
    task_nodes = graph.get_predecessors(var, node_type=Task, edge_type=Def)
    assert len(task_nodes) == 1, (
        f"Internal Error: Expected one task node found for registered variable {var!r}, found {len(task_nodes)}"
    )
    task_node = task_nodes[0]

    return bool(graph.get_predecessors(task_node, edge_type=When))


class ValueChangeReason(Enum):
    EXPRESSION_IMPURE = 1
    DEPENDENCY_REDEFINED = 2
    DEPENDENCY_VALUE_CHANGED = 3


def determine_value_version_change_reason(
    graph: Graph, v1: Variable, v2: Variable
) -> tuple[ValueChangeReason, Expression | tuple[Variable, Variable] | None]:
    e1 = get_def_expression(graph, v1)
    e2 = get_def_expression(graph, v2)
    assert e1 is not None and e2 is not None, (
        f"It should not be possible for variables {v1!r} and {v2!r} to not have been defined!"
    )
    assert e1.expr == e2.expr and e1.is_pure == e2.is_pure, (
        f"Variables {v1!r} and {v2!r} use different expressions"
    )

    if not e1.is_pure:
        return ValueChangeReason.EXPRESSION_IMPURE, e1

    e1_uses = set(get_used_variables(graph, e1))
    e2_uses = set(get_used_variables(graph, e2))
    assert len(e1_uses) == len(e2_uses), (
        f"Expressions used by {v1!r} and {v2!r} use different number of values"
    )
    common_uses = e1_uses & e2_uses
    assert len(common_uses) < len(e1_uses), (
        f"Expressions used by {v1!r} and {v2!r} share all variable uses and are pure, yet still have different value versions"
    )

    unique_e1_uses = sorted(e1_uses - common_uses, key=lambda v: v.name)
    unique_e2_uses = sorted(e2_uses - common_uses, key=lambda v: v.name)

    diff_uses = list(zip(unique_e1_uses, unique_e2_uses))

    redefined = False
    redefined_context: tuple[Variable, Variable] | None = None
    diff_value_version = False
    for e1_use, e2_use in diff_uses:
        assert e1_use.name == e2_use.name, (
            f"Expressions used by {v1!r} and {v2!r} should be identical, but use variables with different names: The former uses {e1_use.name}, the latter uses {e2_use.name}"
        )
        this_redefined = e1_use.version != e2_use.version
        this_diff_value_version = (
            not redefined and e1_use.value_version != e2_use.value_version
        )

        redefined = redefined or this_redefined
        diff_value_version = diff_value_version or this_diff_value_version

        if redefined:
            redefined_context = (e1_use, e2_use)

    assert redefined or diff_value_version, (
        f"Could not find any difference between {v1!r} and {v2!r}"
    )
    if redefined:
        assert redefined_context is not None
        return ValueChangeReason.DEPENDENCY_REDEFINED, redefined_context
    else:
        return ValueChangeReason.DEPENDENCY_VALUE_CHANGED, None


def find_variable_usages(
    graph: Graph, variable: Variable, indirection_chain: list[str] | None = None
) -> set[str]:
    usages = graph.get_successors(variable, node_type=Expression, edge_type=Use)
    if not usages:
        assert not graph.has_successor(variable), (
            f"Variable {variable!r} has successors but is not used in any expression"
        )

    usage_descriptions: set[str] = set()
    for usage in usages:
        expr_ivs = graph.get_successors(
            usage, node_type=IntermediateValue, edge_type=Def
        )
        assert len(expr_ivs) >= 1, (
            f"Variable {variable!r} is used in expression without defined intermediate values"
        )
        for iv in expr_ivs:
            control_usages = graph.get_successors(
                iv, node_type=ControlNode, edge_type=DataFlowEdge
            )
            indirect_usages = graph.get_successors(
                iv, node_type=Variable, edge_type=Def
            )

            for control_usage in control_usages:
                # if indirection_chain is None:
                usage_descriptions.add(str(control_usage.location))
                # else:
                #     usage_descriptions.add(
                #         control_usage.location
                #         + f' (via {"->".join(indirection_chain)})'
                #     )

            for indirect_usage in indirect_usages:
                new_indirection_chain = indirection_chain or []
                new_indirection_chain.append(indirect_usage.name)
                usage_descriptions.update(
                    find_variable_usages(graph, indirect_usage, new_indirection_chain)
                )

    return usage_descriptions
