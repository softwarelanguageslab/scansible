from __future__ import annotations

from scansible.representations.pdg import Graph, neo4j_dump

from .db import Neo4jDatabase
from .rules import get_all_rules, RuleResult

def run_all_checks(pdg: Graph, db_url: str, db_user: str, db_pass: str) -> list[tuple[str, str]]:
    rules = get_all_rules()
    results = []
    pdg_import_query = neo4j_dump(pdg)

    if not pdg_import_query.strip():
        return []

    with Neo4jDatabase(db_url, db_user, db_pass) as db:
        try:
            db.run(pdg_import_query)
            for rule in rules:
                raw_results = rule.run(db)
                results.extend(_convert_results(raw_results))
        finally:
            db.run(f'MATCH (n {{role_name: "{pdg.role_name}", role_version: "{pdg.role_version}"}}) DETACH DELETE n;')

    return results


def _convert_results(results: list[RuleResult]) -> list[tuple[str, str]]:
    new_results = []
    for name, source_loc, sink_loc, _ in results:
        if source_loc == 'unknown file:-1:-1':
            source_loc = sink_loc
        new_results.append((name, sink_loc))

    return new_results
