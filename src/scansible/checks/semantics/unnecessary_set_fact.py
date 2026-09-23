from __future__ import annotations

from typing import final, override

from scansible.pdg.builder.semantics import EnvironmentType
from scansible.pdg.representation import Graph, Literal, Task, Variable

from ..base import Finding
from .base import TraversalRule
from .utils import get_def_conditions, get_var_origin, is_pure_expr


@final
class UnnecessarySetFactRule(TraversalRule):
    code = "SEM002"

    @override
    def detect(self, graph: Graph) -> list[Finding]:
        set_facted_vars = [
            node
            for node in graph.get_nodes(Variable)
            if node.scope_level == EnvironmentType.SET_FACTS_REGISTERED.value
        ]

        results: list[Finding] = []
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

            if not (is_pure_def and is_pure_condition):
                continue

            summary = f"Unnecessary use of set_fact for variable `{v.name}@{v.version}`"
            explanation = (
                "This variable's initialiser and conditions are fully pure. "
                "Evaluating it eagerly serves no purpose, "
                "the same result can likely be achieved at lower precedence."
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
