from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar, override

import abc
from collections.abc import Mapping
from textwrap import dedent

from loguru import logger
from pydantic import TypeAdapter

from ...base import CheckContext, Finding, RuleBase
from ..db import DatabaseResultConverter, DatabaseValue, GraphDatabase, unescape_string

if TYPE_CHECKING:
    from scansible.pdg.representation import NodeLocation

type RuleParameters = Mapping[str, DatabaseValue]
type RuleQuery = tuple[str, RuleParameters]

# Note: Cannot use `type` statements here as we need these as values.
RuleQueryResult = tuple[int, int, str]
LocationQueryResult = tuple[int]


def _validate_query_result[T](result_type: type[T]) -> DatabaseResultConverter[T]:
    return TypeAdapter(result_type).validate_python


class GraphDBRule(RuleBase, abc.ABC):
    """Base class for security rules that detect issues through Cypher queries over the graph DB."""

    #: Rule-level rationale, folded into every finding's `explanation`.
    description: ClassVar[str]

    @property
    @abc.abstractmethod
    def query(self) -> RuleQuery:
        """Return the Cypher query (and its parameters) identifying (source, sink, label) triples."""
        raise NotImplementedError

    @abc.abstractmethod
    def describe(self, label: str) -> str:
        """Build a finding-specific one-line summary from the query's label column."""
        raise NotImplementedError

    def _get_location(self, db: GraphDatabase, node_id: int) -> NodeLocation:
        """Get source code location of a node."""
        node_location = db.get_location(node_id)
        # Node may not have location information stored (e.g., scalar literals),
        # so get location of the node it is assigned to.
        while node_location.is_synthetic:
            assigned_nodes = db.query(
                _validate_query_result(LocationQueryResult),
                "MATCH (n) -[:e_Def|e_Keyword]->(n2) WHERE n.node_id = $node_id RETURN n2.node_id",
                parameters={"node_id": node_id},
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

    @override
    def check(self, context: CheckContext) -> list[Finding]:
        assert context.db is not None, (
            f"{type(self).__name__} requires a graph database"
        )
        db = context.db

        query, query_params = self.query
        query = dedent(query).strip()
        raw_results = db.query(
            _validate_query_result(RuleQueryResult), query, query_params
        )

        findings: list[Finding] = []
        for source, sink, raw_label in raw_results:
            label = unescape_string(raw_label)
            sink_loc = self._get_location(db, sink)
            source_loc = self._get_location(db, source)
            hint_location, hint_text = (
                (source_loc, "value originates here")
                if source_loc != sink_loc
                else (None, "")
            )
            findings.append(
                Finding(
                    code=self.code,
                    summary=self.describe(label),
                    explanation=self.description,
                    location=sink_loc,
                    hint_location=hint_location,
                    hint_text=hint_text,
                )
            )

        return findings
