from __future__ import annotations

from typing import override

from scansible.pdg.representation import Graph, NodeLocation, Task

from .base import Rule, RuleResult


class SanityCheckNumberOfTasksRule(Rule):
    @override
    def scan(self, graph: Graph) -> list[RuleResult]:
        num_tasks = len(graph.get_nodes(Task))
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
                rule_header="Found no or very few tasks, something may have gone wrong with PDG building.",
                rule_message="",
                location=NodeLocation(file="tasks/main.yml", line=1, column=1),
            )
        ]
