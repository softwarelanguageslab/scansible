from __future__ import annotations

from typing import TYPE_CHECKING

from scansible.checks.base import CheckContext, Finding
from scansible.checks.semantics import get_all_rules
from scansible.pdg import build_pdg

if TYPE_CHECKING:
    from pathlib import Path

    from scansible.pdg.builder.context import BuildContext

#: A `Finding`, but with each `NodeLocation` collapsed down to its
#: `path:line:column` string to avoid deep positioning checks in tests.
type StringifiedResult = tuple[str, str, str, str | None]


def _stringify(results: list[Finding]) -> list[StringifiedResult]:
    return [
        (
            f.code,
            f.summary,
            str(f.location),
            str(f.hint_location) if f.hint_location is not None else None,
        )
        for f in results
    ]


def run_all_checks(ctx: BuildContext) -> list[StringifiedResult]:
    context = CheckContext(graph=ctx.graph)
    results = [finding for rule in get_all_rules() for finding in rule.check(context)]
    return _stringify(results)


def build_graph(path: Path) -> BuildContext:
    return build_pdg(path, [])


def write_yaml(content: str, path: Path) -> None:
    _ = path.write_text(content)
