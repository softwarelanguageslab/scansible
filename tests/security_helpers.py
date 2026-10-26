from __future__ import annotations

from typing import TYPE_CHECKING

import sys
from contextlib import contextmanager

from loguru import logger

from scansible.checks.base import CheckContext, Finding
from scansible.checks.security import rules
from scansible.checks.security.db import GraphDatabase
from scansible.pdg import build_pdg

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@contextmanager
def temp_import_pb(path: Path) -> Generator[CheckContext]:
    logger.remove()
    pdg_ctx = build_pdg(path, [])
    _ = logger.add(sys.stderr, format="{level} {message}", level="DEBUG")
    with GraphDatabase(pdg_ctx.graph) as graph_db:
        yield CheckContext(graph=pdg_ctx.graph, db=graph_db)


def write_pb(content: str, path: Path) -> None:
    _ = path.write_text(content)


#: A `Finding`, but with each `NodeLocation` collapsed down to its
#: `path:line:column` string to avoid deep positioning checks in tests.
type StringifiedResult = tuple[str, str, str, str | None]


def make_result(
    code: str, summary: str, location: str, hint_location: str | None = None
) -> StringifiedResult:
    return (code, summary, location, hint_location)


def stringify(results: list[Finding]) -> list[StringifiedResult]:
    return [
        make_result(
            f.code,
            f.summary,
            str(f.location),
            str(f.hint_location) if f.hint_location is not None else None,
        )
        for f in results
    ]


def run_all_checks(context: CheckContext) -> list[StringifiedResult]:
    results: list[Finding] = []
    for rule in rules.get_all_rules():
        results.extend(rule.check(context))
    return stringify(results)
