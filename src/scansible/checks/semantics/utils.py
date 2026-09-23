from __future__ import annotations

from typing import NamedTuple

from scansible.pdg.builder.semantics import EnvironmentType
from scansible.pdg.representation import (
    ControlNode,
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


class DependencyWalk(NamedTuple):
    #: Whether the expression this walk started from is itself pure.
    root_is_pure: bool
    #: name -> the Variable (this value-version) transitively used to compute the root.
    used_definitions: dict[str, Variable]
    #: name -> purity of that Variable's own defining expression (True if it has none,
    #: e.g. a literal or externally-supplied value).
    definition_is_pure: dict[str, bool]


def walk_data_dependencies(graph: Graph, expr: Expression) -> DependencyWalk:
    """Transitively walk `expr`'s data dependencies (Use -> Variable -> Def -> Expression,
    recursively), collecting every variable definition used and the purity of each one's
    own defining expression, plus the purity of `expr` itself."""
    used_definitions: dict[str, Variable] = {}
    definition_is_pure: dict[str, bool] = {}
    _walk_data_dependencies(graph, expr, used_definitions, definition_is_pure, set())
    return DependencyWalk(expr.is_pure, used_definitions, definition_is_pure)


def _walk_data_dependencies(
    graph: Graph,
    expr: Expression,
    used_definitions: dict[str, Variable],
    definition_is_pure: dict[str, bool],
    visited: set[int],
) -> None:
    if expr.node_id in visited:
        return
    visited.add(expr.node_id)

    for v in get_used_variables(graph, expr):
        used_definitions[v.name] = v
        sub_expr = get_def_expression(graph, v)
        definition_is_pure[v.name] = sub_expr.is_pure if sub_expr is not None else True
        if sub_expr is not None:
            _walk_data_dependencies(
                graph, sub_expr, used_definitions, definition_is_pure, visited
            )
