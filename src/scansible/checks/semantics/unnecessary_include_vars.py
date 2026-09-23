from __future__ import annotations

from typing import final, override

from collections import defaultdict

from scansible.pdg.builder.semantics import EnvironmentType
from scansible.pdg.representation import Graph, Variable

from ..base import Finding
from .base import TraversalRule
from .utils import get_def_conditions


@final
class UnnecessaryIncludeVarsRule(TraversalRule):
    code = "SEM003"

    @override
    def detect(self, graph: Graph) -> list[Finding]:
        included_vars = [
            node
            for node in graph.get_nodes(Variable)
            if node.scope_level == EnvironmentType.INCLUDE_VARS.value
        ]
        # Group into unique definitions so we only emit a warning for the first value version
        grouped_included_vars: dict[tuple[str, int], set[Variable]] = defaultdict(set)
        for v in included_vars:
            grouped_included_vars[(v.name, v.version)].add(v)

        results: list[Finding] = []
        for vs in grouped_included_vars.values():
            v = min(vs, key=lambda v: v.version)
            conditions = get_def_conditions(graph, v)

            if not conditions:
                summary = f"Unnecessary use of include_vars for variable `{v.name}@{v.version}`"
                explanation = (
                    "This variable is unconditionally included through include_vars, "
                    "which has unusually high precedence and makes tracing values difficult. "
                    "It can instead be placed into default variables, role variables, or a "
                    "local scope, to avoid variable precedence issues."
                )
                results.append(
                    Finding(
                        code=self.code,
                        summary=summary,
                        explanation=explanation,
                        location=v.location,
                    )
                )

        return results
