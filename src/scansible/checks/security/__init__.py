from __future__ import annotations

from typing import Any

from datetime import datetime

from loguru import logger

from scansible.representations.pdg import Graph, neo4j_dump

from .db import RedisGraphDatabase
from .rules import get_all_rules, RuleResult, Rule

def run_all_checks(pdg: Graph, db_host: str) -> list[tuple[str, str]]:
    rules = get_all_rules()
    pdg_import_query = neo4j_dump(pdg)

    if not pdg_import_query.strip():
        return []

    start_time = datetime.now()
    db = RedisGraphDatabase(db_host)

    with db.temporary_graph(f'{pdg.role_name}@{pdg.role_version}', pdg_import_query) as graph:
        logger.info(f'Imported graph of {len(pdg)} nodes and {len(pdg.edges())} edges in {(datetime.now() - start_time).total_seconds():.2f}s')
        results = run_checks(pdg, rules)

    logger.info(f'Running checks took a total of {(datetime.now() - start_time).total_seconds():.2f}s')
    return results

def run_checks(graph_db: Any, rules: list[Rule]) -> list[tuple[str, str]]:
    results = set()

    prev_time = datetime.now()
    for rule in rules:
        raw_results = rule.run(graph_db)
        results |= _convert_results(raw_results)
    logger.info(f'Ran queries in {(datetime.now() - prev_time).total_seconds():.2f}s')
    prev_time = datetime.now()

    logger.info(f'Cleaned up in {(datetime.now() - prev_time).total_seconds():.2f}s')

    return sorted(results, key=lambda res: res[1])


def _convert_results(results: list[RuleResult]) -> set[tuple[str, str]]:
    new_results = set()
    for name, source_loc, sink_loc, _ in results:
        if source_loc == 'unknown file:-1:-1':
            source_loc = sink_loc
        new_results.add((name, source_loc))

    return new_results
