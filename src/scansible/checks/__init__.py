from __future__ import annotations

from typing import TYPE_CHECKING

from datetime import datetime

from loguru import logger

from . import security as security
from . import semantics as semantics
from .base import CheckContext, RuleBase
from .base import Finding as Finding
from .reporter import TerminalReporter as TerminalReporter
from .security.db import GraphDatabase
from .security.rules.base import GraphDBRule

if TYPE_CHECKING:
    from scansible.pdg.builder.context import BuildContext


def get_all_rules() -> list[RuleBase]:
    return [*security.get_all_rules(), *semantics.get_all_rules()]


def run_all_checks(
    build_context: BuildContext,
    *,
    enable_security: bool = True,
    enable_semantics: bool = True,
) -> list[Finding]:
    start_time = datetime.now()

    rules = [
        rule
        for rule in get_all_rules()
        if (enable_security if rule.code.startswith("SEC") else enable_semantics)
    ]

    graph = build_context.graph
    if any(isinstance(rule, GraphDBRule) for rule in rules):
        with GraphDatabase(graph) as db:
            results = [
                finding
                for rule in rules
                for finding in rule.check(CheckContext(graph, db))
            ]
    else:
        results = [
            finding for rule in rules for finding in rule.check(CheckContext(graph))
        ]

    logger.info(
        f"Ran {len(rules)} checks in {(datetime.now() - start_time).total_seconds():.2f}s"
    )

    return sorted(results, key=lambda finding: str(finding.location))
