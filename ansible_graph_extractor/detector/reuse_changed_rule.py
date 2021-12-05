from collections.abc import Collection, Iterable
from collections import defaultdict

from ..models.graph import Graph
from ..models.nodes import Expression, IntermediateValue, Variable
from ..models.edges import Def
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


class ReuseChangedVariableRule(Rule):
    def scan(self, graph: Graph) -> list[RuleResult]:
        var_nodes = [node for node in graph.nodes() if isinstance(node, Variable)]
        name_to_vars = defaultdict(set)
        for node in var_nodes:
            name_to_vars[(node.name, node.version)].add(node)

        results: list[RuleResult] = []
        for related_nodes in name_to_vars.values():
            results.extend(self.scan_vars(graph, related_nodes))
        return results

    def scan_vars(self, graph: Graph, nodes: Collection[Variable]) -> Iterable[RuleResult]:
        assert len({node.value_version for node in nodes}) == len(nodes), 'Somehow different nodes with same value version?!'
        if len(nodes) <= 1:
            return

        node_to_expr = {n: expr for n in nodes if (expr := get_def_expression(graph, n)) is not None}
        node_sorted = sorted(node_to_expr.keys(), key=lambda n: n.value_version)
        for prev_usage, curr_usage in zip(node_sorted, node_sorted[1:]):
            if node_to_expr[prev_usage] == node_to_expr[curr_usage]:
                continue
            desc = '\n'.join([
                'Potential unsafe reuse of variable whose value may have been changed.',
                f'Variable {curr_usage.name}@{curr_usage.version} was previously used with value version {prev_usage.value_version}, but now with {curr_usage.value_version}',
                'A dependency of the expression may have been changed, causing it to be re-evaluated.'])
            yield RuleResult(rule_name='UnsafeReuseChangedVars', role_name=graph.role_name, description=desc)
