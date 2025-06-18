from __future__ import annotations

from typing import Any, ClassVar, NamedTuple, Sequence

import abc
import json

from loguru import logger

from scansible.checks.security.db import GraphDatabase
from scansible.representations.pdg.representation import NodeLocation


# TODO: Locations should use NodeLocation.
class RuleResult(NamedTuple):
    #: The rule that was triggered.
    rule_name: str
    #: Rule description
    rule_description: str
    #: Location in the code of the source of the smell
    source_location: str | None
    #: Location in the code of the sink of the smell
    sink_location: str | None


def _convert_location(loc: NodeLocation | None) -> str:
    if loc is None:
        return "unknown file:-1:-1"
    return str(loc)
    # return ":".join(map(str, (loc.file, loc.line, loc.column)))


class Rule(abc.ABC):
    name: ClassVar[str] = ""
    short_name: ClassVar[str] = ""
    description: ClassVar[str]

    def __init_subclass__(cls, **kwargs: object) -> None:
        super().__init_subclass__(**kwargs)

        if not cls.name:
            cls.name = cls.__name__.removesuffix("Rule")
        if not cls.short_name:
            cls.short_name = cls.__name__.removesuffix("Rule")

    @property
    @abc.abstractmethod
    def query(self) -> tuple[str, dict[str, Any]]:
        raise NotImplementedError("To be implemented by subclass")

    def _get_location(self, db: GraphDatabase, node_id: int) -> NodeLocation | None:
        """Get source code location of a node."""
        node_location = db.get_location(node_id)
        # Node may not have location information stored (e.g., scalar literals),
        # so get location of the node it is assigned to.
        while node_location is None or node_location.file == "unknown file":
            assigned_nodes = list(
                db.query(
                    "MATCH (n) -[:e_Def|e_Keyword]->(n2) WHERE n.node_id = $node_id RETURN n2.node_id",
                    parameters={"node_id": node_id},
                )
            )

            if not assigned_nodes:
                logger.error(
                    f"Node with ID {node_id} is not assigned, cannot get location"
                )
                break
            if len(assigned_nodes) > 1:
                logger.error(
                    f"Node with ID {node_id} is assigned multiple times, cannot get location"
                )
                break

            node_id = assigned_nodes[0][0]
            node_location = db.get_location(node_id)

        return node_location

    def run(self, graph_db: GraphDatabase) -> list[RuleResult]:
        query, query_params = self.query
        raw_results = graph_db.query(query, query_params)

        results: list[RuleResult] = []
        for source, sink in raw_results:
            results.append(
                RuleResult(
                    self.short_name,
                    self.description,
                    _convert_location(self._get_location(graph_db, source)),
                    _convert_location(self._get_location(graph_db, sink)),
                )
            )

        return results
