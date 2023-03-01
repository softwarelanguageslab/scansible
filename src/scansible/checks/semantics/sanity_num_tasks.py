from scansible.representations.pdg.extractor.context import \
    VisibilityInformation
from scansible.representations.pdg.representation import (Graph, NodeLocation,
                                                          Task)

from .base import Rule, RuleResult
from .utils import get_nodes


class SanityCheckNumberOfTasksRule(Rule):
    def scan(self, graph: Graph, visinfo: VisibilityInformation) -> list[RuleResult]:
        num_tasks = len(get_nodes(graph, Task))
        if num_tasks > 2:
            return []

        if not num_tasks:
            rule_name = "No tasks found"
            rule_subname = ""
        else:
            rule_name = "Few tasks found"
            rule_subname = f"Only found {num_tasks} tasks"

        return [
            RuleResult(
                rule_category="Sanity checks",
                rule_name=rule_name,
                rule_subname=rule_subname,
                rule_header="Found no or very few tasks, something may have gone wrong with extraction",
                rule_message="",
                role_name=graph.role_name,
                role_version=graph.role_version,
                location=NodeLocation("tasks/main.yml", 1, 1),
            )
        ]
