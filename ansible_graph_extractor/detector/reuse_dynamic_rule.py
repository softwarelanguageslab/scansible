from collections.abc import Iterable
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


class ReuseDynamicExpressionRule(Rule):
    def scan(self, graph: Graph) -> list[RuleResult]:
        var_nodes = [node for node in graph.nodes() if isinstance(node, Variable)]
        name_to_vars = defaultdict(set)
        for node in var_nodes:
            name_to_vars[node.name].add(node)

        results: list[RuleResult] = []
        for related_nodes in name_to_vars.values():
            results.extend(self.scan_vars(graph, related_nodes))
        return results

    def scan_vars(self, graph: Graph, nodes: Iterable[Variable]) -> Iterable[RuleResult]:
        versions_to_nodes: dict[int, set[Variable]] = defaultdict(set)
        for node in nodes:
            versions_to_nodes[node.version].add(node)
        for same_expr_nodes in versions_to_nodes.values():
            assert len({node.value_version for node in same_expr_nodes}) == len(same_expr_nodes), 'Somehow different nodes with same value version?!'
            if len(same_expr_nodes) <= 1:
                continue
            expr_to_nodes: dict[Expression, set[Variable]] = defaultdict(set)
            for node in same_expr_nodes:
                expr = get_def_expression(graph, node)
                if expr is not None:
                    expr_to_nodes[expr].add(node)

            for expr, nodes in expr_to_nodes.items():
                nodes_sorted = sorted(nodes, key=lambda node: node.value_version)
                for node in nodes_sorted[1:]:
                    desc = '\n'.join([
                        'Potential unsafe reuse of variable whose value may have been changed.',
                        f'Variable {node.name} is defined with expression {expr.expr}, which is dynamic and has been used before.',
                    ])
                    yield RuleResult(rule_name='UnsafeReuseNotIdempotent', role_name=graph.role_name, description=desc)
