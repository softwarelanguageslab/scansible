from collections.abc import Collection, Iterable
from collections import defaultdict

from ..models.graph import Graph
from ..models.nodes import Expression, Literal, IntermediateValue, Variable, Task
from ..models.edges import Def, DefinedIf
from ..extractor.var_context import ScopeLevel
from .base import Rule, RuleResult

def get_def_expression(graph: Graph, node: Variable) -> Expression | None:
    # Need to follow intermediate value first
    ivs = [pred for pred in graph.predecessors(node) if isinstance(pred, IntermediateValue)]
    assert sum(1 for succ in graph.successors(node) if isinstance(succ, IntermediateValue)) < 2, f'Variable with multiple defined IVs?! {node.name} in {graph.role_name}'
    assert len(ivs) < 2, f'Variable with multiple defining IVs?! {node.name} in {graph.role_name}'
    if not ivs:
        return None
    assert isinstance(graph[ivs[0]][node][0]['type'], Def), 'Non-DEF IV?!'

    exprs = [pred for pred in graph.predecessors(ivs[0]) if isinstance(pred, Expression) and isinstance(graph[pred][ivs[0]][0]['type'], Def)]
    assert len(exprs) < 2, 'IV with multiple DEFs?!'
    return exprs[0] if exprs else None


def get_iv_expr(graph: Graph, node: IntermediateValue) -> Expression | None:
    exprs = [
        expr for expr in graph.predecessors(node)
        if isinstance(graph[expr][node][0]['type'], Def)]
    assert len(exprs) == 1, f'Expected IV with 1 DEF, got {len(exprs)} nodes for IV ${node.identifier}'
    assert isinstance(exprs[0], Expression), 'What is this IV defined by?!'
    return exprs[0] if exprs else None


def get_var_origin(graph: Graph, node: Variable) -> Expression | Literal | Task | None:
    preds = graph.predecessors(node)
    def_preds = [pred for pred in preds if isinstance(graph[pred][node][0]['type'], Def)]
    def_task = next((pred for pred in def_preds if isinstance(pred, Task)), None)
    if def_task is not None:
        # register, not set_fact. For register, it's possible for the variable
        # to have multiple DEFs (e.g. task itself and loop)
        return def_task
    assert len(def_preds) < 2, f'Variable with multiple DEF predecessors?! {node.name} in {graph.role_name}'
    if not def_preds:
        return None

    def_pred = def_preds[0]
    if isinstance(def_pred, (Task, Literal)):
        return def_pred
    assert isinstance(def_pred, IntermediateValue), f'Non-IV DEF predecessor?! {node.name} in {graph.role_name}'

    # Find expression for IV
    return get_iv_expr(graph, def_pred)


def is_idempotent_expr(graph: Graph, expr: Expression) -> bool:
    if not expr.idempotent:
        return False

    # Expression itself is idempotent, but perhaps its dependences aren't
    # Find used variables
    used_nodes = [v for v in graph.predecessors(expr) if isinstance(graph[v][expr][0]['type'], Def)]
    assert all(isinstance(v, Variable) for v in used_nodes), 'Expression uses non-variable?!'
    # Find definitions of uses
    used_defs: list[Expression] = [
        def_expr for used_node in used_nodes
        if isinstance((def_expr := get_var_origin(graph, used_node)), Expression)]

    if not used_defs:
        return True

    return all(is_idempotent_expr(graph, d) for d in used_defs)


def get_conditions(graph: Graph, v: Variable) -> list[Expression]:
    cond_ivs = [
        c for c in graph.predecessors(v)
        if isinstance(graph[c][v][0]['type'], DefinedIf)]
    cond_exprs: list[Expression] = []
    for civ in cond_ivs:
        if isinstance(civ, Literal):
            continue
        expr = get_iv_expr(graph, civ)
        assert isinstance(expr, Expression), 'Conditional definition without condition expression?!'
        cond_exprs.append(expr)

    return cond_exprs


class UnnecessarySetFactRule(Rule):
    def scan(self, graph: Graph) -> list[RuleResult]:
        set_facted_vars = [
            node for node in graph.nodes()
            if isinstance(node, Variable) and node.scope_level == ScopeLevel.SET_FACTS_REGISTERED.value]

        results: list[RuleResult] = []
        for v in set_facted_vars:
            vorigin = get_var_origin(graph, v)
            assert vorigin is not None, 'set_fact without definition?!'
            if isinstance(vorigin, Task):
                # register, not set_fact
                continue
            is_idempotent_def = (not isinstance(vorigin, Expression)) or is_idempotent_expr(graph, vorigin)
            conditions = get_conditions(graph, v)
            is_idempotent_condition = (not conditions) or all(is_idempotent_expr(graph, cond) for cond in conditions)

            if is_idempotent_def and is_idempotent_condition:
                lines = ['Unnecessary use of set_fact on idempotent expression']
                if isinstance(vorigin, Literal):
                    lines.append(f'Variable {v.name}@{v.version} is defined the literal `{vorigin.value}`')
                else:
                    lines.append(f'Variable {v.name}@{v.version} is defined the expression `{vorigin.expr}`, which is fully idempotent')
                if conditions:
                    lines.append('Moreover, all conditionals for this variable are idempotent:')
                    lines.extend([f'`{condition.expr}`' for condition in conditions])
                lines.append('Therefore, greedily evaluating this variable serves no purpose and identical results can be achieved at lower precedences.')
                results.append(RuleResult(rule_name='UnnecessarySetFact', role_name=graph.role_name, description='\n'.join(lines)))
            else:
                results.append(RuleResult(rule_name='NecessarySetFact', role_name=graph.role_name, description=f'{v.name} with {vorigin}'))

        return results
