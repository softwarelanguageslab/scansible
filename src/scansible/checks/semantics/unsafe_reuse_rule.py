from __future__ import annotations

from typing import TYPE_CHECKING, NamedTuple, final, override

from collections import defaultdict
from itertools import pairwise

from scansible.pdg.builder.semantics import EnvironmentType
from scansible.pdg.representation import Expression, Graph, Variable

from ..base import Finding
from .base import TraversalRule
from .utils import get_def_expression, walk_data_dependencies

if TYPE_CHECKING:
    from collections.abc import Iterable

    from scansible.pdg.representation import NodeLocation

    from .utils import DependencyWalk


class _ReuseVerdict(NamedTuple):
    """Why a variable reuse might be unsafe, as determined by comparing two consecutive evaluations."""

    #: Pairs of variables that were redefined.
    changed: list[tuple[Variable, Variable]]
    #: Variables with lazily-evaluated impure initialisers.
    impure_deps: list[Variable]
    #: Whether the root variable's own initialiser is impure.
    is_root_impure: bool

    def __bool__(self) -> bool:
        return bool(self.changed or self.impure_deps or self.is_root_impure)


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


def _build_summary(v2: Variable, verdict: _ReuseVerdict) -> str:
    """Build the summary for a finding."""
    reasons: list[str] = []
    if verdict.is_root_impure or verdict.impure_deps:
        reasons.append("an impure expression")
    if verdict.changed:
        reasons.append("a redefined dependency")
    return f"Potentially unsafe reuse of variable `{v2.name}@{v2.version}` due to {' and '.join(reasons)}"


def _build_explanation(
    v1: Variable, v2: Variable, e2: Expression, verdict: _ReuseVerdict
) -> str:
    """Build the explanation for why a variable reuse is considered unsafe."""
    first_part = (
        f"This is value version {v2.value_version} of `{v2.name}@{v2.version}`; "
        f"the previous evaluation was value version {v1.value_version}."
    )
    explanation_parts = [first_part]

    if verdict.is_root_impure:
        components = ", ".join(sorted(e2.impure_components))
        explanation_parts.append(
            f"Its own defining expression `{e2.expr}` is impure, due to: {components}."
        )
    if verdict.impure_deps:
        names = ", ".join(sorted({d.name for d in verdict.impure_deps}))
        explanation_parts.append(
            f"It depends on `{names}`, which is lazily re-evaluated and impure."
        )
    if verdict.changed:
        names = ", ".join(sorted({d1.name for d1, _ in verdict.changed}))
        explanation_parts.append(
            f"It depends on `{names}`, which has been redefined since the "
            + "previous evaluation."
        )

    return " ".join(explanation_parts)


def _select_hint(
    graph: Graph, v2: Variable, e2: Expression, verdict: _ReuseVerdict
) -> tuple[NodeLocation | None, str]:
    """Pick the most relevant secondary location to point at, if any."""
    if verdict.changed:
        return verdict.changed[0][1].location, "dependency redefined here"
    if verdict.is_root_impure:
        if e2.location != v2.location:
            return e2.location, "impure expression here"
        return None, ""
    if verdict.impure_deps:
        dep_expr = get_def_expression(graph, verdict.impure_deps[0])
        if dep_expr is not None and dep_expr.location != v2.location:
            return dep_expr.location, "impure expression here"
    return None, ""


def _compare_dependencies(
    walk1: DependencyWalk, walk2: DependencyWalk
) -> _ReuseVerdict:
    changed: list[tuple[Variable, Variable]] = []
    impure_deps: list[Variable] = []
    for name in sorted(walk1.used_definitions.keys() & walk2.used_definitions.keys()):
        d1 = walk1.used_definitions[name]
        d2 = walk2.used_definitions[name]
        if d1.version != d2.version:
            changed.append((d1, d2))
        elif (
            d1.value_version != d2.value_version and not walk2.definition_is_pure[name]
        ):
            impure_deps.append(d2)

    return _ReuseVerdict(
        changed=changed,
        impure_deps=impure_deps,
        is_root_impure=not walk2.root_is_pure,
    )


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

            verdict = _compare_dependencies(walk1, walk2)

            if not verdict:
                # Same definitions used, everything involved is pure -> guaranteed
                # same value, the value-version bump is just re-evaluation noise.
                continue

            summary = _build_summary(v2, verdict)
            explanation = _build_explanation(v1, v2, e2, verdict)

            hint_location, hint_text = _select_hint(graph, v2, e2, verdict)

            results.append(
                Finding(
                    code=UnsafeReuseRule.code,
                    summary=summary,
                    explanation=explanation,
                    location=v2.location,
                    hint_location=hint_location,
                    hint_text=hint_text,
                )
            )

        return results
