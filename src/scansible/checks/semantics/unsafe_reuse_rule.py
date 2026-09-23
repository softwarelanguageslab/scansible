from __future__ import annotations

from typing import final, override

from collections import defaultdict
from collections.abc import Iterable
from itertools import pairwise

from scansible.pdg.builder.semantics import EnvironmentType
from scansible.pdg.representation import Graph, Variable

from ..base import Finding
from .base import TraversalRule
from .utils import get_def_expression, walk_data_dependencies


def _find_consecutive_values(
    var_nodes: Iterable[Variable],
) -> Iterable[tuple[Variable, Variable]]:
    """Yield consecutive (prev, next) value-version pairs of the same variable definition."""
    var_name_to_vars: dict[tuple[str, int], set[Variable]] = defaultdict(set)
    for node in var_nodes:
        if node.scope_level == EnvironmentType.UNDEFINED.value:
            # Ignore undefined variables.
            continue
        var_name_to_vars[(node.name, node.version)].add(node)

    for nodes in var_name_to_vars.values():
        assert len({node.value_version for node in nodes}) == len(nodes), (
            "Somehow different nodes with same value version?!"
        )
        # If there's only one value for this variable version, there are no consecutive evaluations.
        if len(nodes) <= 1:
            continue

        nodes_sorted = sorted(nodes, key=lambda n: n.value_version)
        yield from pairwise(nodes_sorted)


@final
class UnsafeReuseRule(TraversalRule):
    """Find lazily-evaluated variables whose value might differ from a previous evaluation.

    Every reuse of a lazily-evaluated variable re-evaluates its defining expression from scratch,
    so consecutive evaluations (value-versions) of the same definition can differ even when nothing
    meaningful changed. Instead, we compare the full transitive data dependencies of two consecutive evaluations.
    If they used the exact same variable *definitions* and every expression involved is pure or eagerly evaluated,
    the two evaluations are guaranteed to produce the same value.
    Otherwise, the reuse might be unsafe, for one or both reasons:
    - Some lazily-evaluated initialiser expression involved is impure, so its value could differ even with unchanged dependencies.
    - One of the dependencies has itself been redefined (a different `version`, not just a different `value_version`).
    """

    code = "SEM001"

    @override
    def detect(self, graph: Graph) -> list[Finding]:
        results: list[Finding] = []
        for v1, v2 in _find_consecutive_values(graph.get_nodes(Variable)):
            e1 = get_def_expression(graph, v1)
            e2 = get_def_expression(graph, v2)
            if e1 is None or e2 is None:
                continue  # externally supplied/registered, not this rule's concern

            walk1 = walk_data_dependencies(graph, e1)
            walk2 = walk_data_dependencies(graph, e2)

            changed: list[tuple[Variable, Variable]] = []
            impure_deps: list[Variable] = []
            for name in sorted(
                walk1.used_definitions.keys() & walk2.used_definitions.keys()
            ):
                d1 = walk1.used_definitions[name]
                d2 = walk2.used_definitions[name]
                if d1.version != d2.version:
                    changed.append((d1, d2))
                elif (
                    d1.value_version != d2.value_version
                    and not walk2.definition_is_pure[name]
                ):
                    impure_deps.append(d2)

            is_root_impure = not walk2.root_is_pure
            if not changed and not is_root_impure and not impure_deps:
                # Same definitions used, everything involved is pure -> guaranteed
                # same value, the value-version bump is just re-evaluation noise.
                continue

            reasons: list[str] = []
            explanation_parts = [
                f"This variable was previously used as {v1!r}, but now as {v2!r}."
            ]
            if is_root_impure or impure_deps:
                reasons.append("an impure expression")
            if changed:
                reasons.append("a redefined dependency")

            if is_root_impure:
                components = ", ".join(sorted(e2.impure_components))
                explanation_parts.append(
                    f"Its own defining expression `{e2.expr}` is impure, due to: {components}."
                )
            if impure_deps:
                names = ", ".join(sorted({d.name for d in impure_deps}))
                explanation_parts.append(
                    f"It depends on `{names}`, which is lazily re-evaluated and impure."
                )
            if changed:
                names = ", ".join(sorted({d1.name for d1, _ in changed}))
                explanation_parts.append(
                    f"It depends on `{names}`, which has been redefined since the "
                    + "previous evaluation."
                )

            summary = (
                f"Potentially unsafe reuse of variable `{v2.name}@{v2.version}` due to "
                f"{' and '.join(reasons)}"
            )

            hint_location = None
            hint_text = ""
            if changed:
                hint_location = changed[0][1].location
                hint_text = "dependency redefined here"
            elif is_root_impure:
                if e2.location != v2.location:
                    hint_location, hint_text = e2.location, "impure expression here"
            elif impure_deps:
                dep_expr = get_def_expression(graph, impure_deps[0])
                if dep_expr is not None and dep_expr.location != v2.location:
                    hint_location, hint_text = (
                        dep_expr.location,
                        "impure expression here",
                    )

            results.append(
                Finding(
                    code=self.code,
                    summary=summary,
                    explanation=" ".join(explanation_parts),
                    location=v2.location,
                    hint_location=hint_location,
                    hint_text=hint_text,
                )
            )
        return results
