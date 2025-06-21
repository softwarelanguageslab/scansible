from __future__ import annotations

from datetime import datetime

from loguru import logger

from scansible.representations.pdg import Graph

from .db import GraphDatabase
from .rules import Rule, RuleResult, get_all_rules


def run_all_checks(pdg: Graph) -> list[RuleResult]:
    rules = get_all_rules()
    return run_checks(pdg, rules)


def run_checks(pdg: Graph, rules: list[Rule]) -> list[RuleResult]:
    start_time = datetime.now()
    results: list[RuleResult] = []
    with GraphDatabase(pdg) as db_graph:
        logger.info(
            f"Imported graph of {pdg.num_nodes} nodes and {pdg.num_edges} edges in {(datetime.now() - start_time).total_seconds():.2f}s"
        )
        prev_time = datetime.now()
        for rule in rules:
            raw_results = rule.run(db_graph)
            results.extend(_convert_results(raw_results))
        logger.info(
            f"Ran queries in {(datetime.now() - prev_time).total_seconds():.2f}s"
        )
        prev_time = datetime.now()

    logger.info(f"Cleaned up in {(datetime.now() - prev_time).total_seconds():.2f}s")
    logger.info(
        f"Running checks took a total of {(datetime.now() - start_time).total_seconds():.2f}s"
    )

    return sorted(results, key=lambda res: res[1])


def _convert_results(results: list[RuleResult]) -> list[RuleResult]:
    return results
