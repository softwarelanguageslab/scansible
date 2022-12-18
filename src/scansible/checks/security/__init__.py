from __future__ import annotations

from typing import Any

from datetime import datetime

from loguru import logger

from scansible.representations.pdg import Graph, neo4j_dump

from .db import RedisGraphDatabase
from .rules import get_all_rules, RuleResult, Rule

def run_all_checks(pdg: Graph, db_host: str) -> list[tuple[str, str, str, int]]:
    rules = get_all_rules()
    return run_checks(pdg, db_host, rules)

def run_checks(pdg: Graph, db_host: str, rules: list[Rule]) -> list[tuple[str, str, str, int]]:
    pdg_import_query = neo4j_dump(pdg)

    if not pdg_import_query.strip():
        return []

    start_time = datetime.now()
    db = RedisGraphDatabase(db_host)

    results = []
    with db.temporary_graph(f'{pdg.role_name}@{pdg.role_version}', pdg_import_query) as db_graph:
        logger.info(f'Imported graph of {len(pdg)} nodes and {len(pdg.edges())} edges in {(datetime.now() - start_time).total_seconds():.2f}s')
        prev_time = datetime.now()
        for rule in rules:
            raw_results = rule.run(db_graph)
            results.extend(_convert_results(raw_results))
        logger.info(f'Ran queries in {(datetime.now() - prev_time).total_seconds():.2f}s')
        prev_time = datetime.now()

    logger.info(f'Cleaned up in {(datetime.now() - prev_time).total_seconds():.2f}s')
    logger.info(f'Running checks took a total of {(datetime.now() - start_time).total_seconds():.2f}s')

    return sorted(results, key=lambda res: res[1])


def _convert_results(results: list[RuleResult]) -> list[tuple[str, str, str, int]]:
    return results  # type: ignore[return-value]
