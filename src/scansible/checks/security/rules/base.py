from __future__ import annotations

from typing import NamedTuple

import abc
import json

from neo4j import Record

from ..db import Neo4jDatabase


class RuleResult(NamedTuple):
    #: The rule that was triggered.
    rule_name: str
    #: Location in the code of the source of the smell (file:line:column)
    source_location: str
    #: Location in the code of the sink of the smell (file:line:column)
    sink_location: str

    #: Level of indirection, i.e. count of intermediate expressions in the data flow path.
    indirection_level: int


def _convert_location(neo_loc: str) -> str:
    loc = json.loads(neo_loc)
    return ':'.join((loc['file'], str(loc['line']), str(loc['column'])))


class Rule(abc.ABC):

    @property
    def name(self) -> str:
        return self.__class__.__name__.removesuffix('Rule')

    @abc.abstractproperty
    def query(self) -> str:
        raise NotImplementedError('To be implemented by subclass')

    def postprocess_results(self, results: list[Record]) -> list[tuple[str, str, int]]:
        return results  # type: ignore[return-value]

    def run(self, db: Neo4jDatabase) -> list[RuleResult]:
        raw_results = db.run(self.query)
        results = []
        for source_location, sink_location, indirection_level in self.postprocess_results(raw_results):
            results.append(RuleResult(self.name, _convert_location(source_location), _convert_location(sink_location), indirection_level))

        return results
