from collections.abc import Collection, Iterable
from collections import defaultdict

from ..models.graph import Graph
from ..models.nodes import Expression, Literal, IntermediateValue, Variable, Task, Node
from ..models.edges import Def, DefinedIf
from ..extractor.var_context import ScopeLevel
from .base import Rule, RuleResult
from .utils import get_nodes, get_node_predecessors, get_def_expression, get_used_variables, get_def_conditions


class SanityCheckNumberOfTasksRule(Rule):
    def scan(self, graph: Graph, visinfo: object) -> list[RuleResult]:
        num_tasks = len(get_nodes(graph, Task))
        if num_tasks > 2:
            return []

        if not num_tasks:
            rule_name = 'No tasks found'
            rule_subname = ''
        else:
            rule_name = 'Few tasks found'
            rule_subname = f'Only found {num_tasks} tasks'

        return [RuleResult(
            rule_category='Sanity checks',
            rule_name=rule_name,
            rule_subname=rule_subname,
            rule_header='Found no or very few tasks, something may have gone wrong with extraction',
            rule_message='',
            role_name=graph.role_name,
            role_version=graph.role_version,
            location='tasks/main.yml')]
