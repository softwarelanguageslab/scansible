from __future__ import annotations

from typing import Protocol, Self, final

import csv
import json
import tempfile
from collections import defaultdict
from collections.abc import Iterator, Mapping, Sequence
from pathlib import Path

import kuzu

from scansible.representations.pdg import Graph
from scansible.representations.pdg.representation import Edge, Node, NodeLocation
from scansible.types import AnyValue

type DatabaseValue = AnyValue

## NOTE: Edges in the graph database are named as "e_<edge type>", e.g., "e_Order",
## as some edge types conflict with reserved keywords in the graph DB queries (e.g., Order).

SCHEMA = """
CREATE NODE TABLE Task(node_id INT64, action STRING, name STRING, PRIMARY KEY (node_id));
CREATE NODE TABLE Variable(node_id INT64, name STRING, version INT64, value_version INT64, scope_level INT64, PRIMARY KEY (node_id));
CREATE NODE TABLE IntermediateValue(node_id INT64, identifier INT64, PRIMARY KEY (node_id));
CREATE NODE TABLE ScalarLiteral(node_id INT64, type STRING, value STRING, PRIMARY KEY (node_id));
CREATE NODE TABLE CompositeLiteral(node_id INT64, type STRING, PRIMARY KEY (node_id));
CREATE NODE TABLE Expression(node_id INT64, expr STRING, is_conditional BOOLEAN, orig_expr STRING, impure_components STRING, PRIMARY KEY (node_id));
CREATE REL TABLE e_Order(FROM Task TO Task, transitive BOOLEAN, back BOOLEAN);
CREATE REL TABLE e_Notifies(FROM Task TO Task);
CREATE REL TABLE e_When(FROM IntermediateValue TO Task, FROM ScalarLiteral TO Task, FROM CompositeLiteral TO Task, FROM IntermediateValue TO Variable, FROM ScalarLiteral TO Variable, FROM CompositeLiteral TO Variable);
CREATE REL TABLE e_Loop(FROM IntermediateValue TO Task, FROM ScalarLiteral TO Task, FROM CompositeLiteral TO Task);
CREATE REL TABLE e_Input(FROM IntermediateValue TO Expression, FROM ScalarLiteral TO Expression, FROM CompositeLiteral TO Expression, FROM Variable TO Expression, param_idx INT8);
CREATE REL TABLE e_Keyword(FROM IntermediateValue TO Task, FROM ScalarLiteral TO Task, FROM CompositeLiteral TO Task, keyword STRING);
CREATE REL TABLE e_Composition(FROM IntermediateValue TO CompositeLiteral, FROM ScalarLiteral TO CompositeLiteral, FROM CompositeLiteral TO CompositeLiteral, index STRING);
CREATE REL TABLE e_Def(FROM Task TO Variable, FROM Expression TO IntermediateValue, FROM IntermediateValue TO Variable, FROM ScalarLiteral TO Variable, FROM CompositeLiteral TO Variable);
CREATE REL TABLE e_DefLoopItem(FROM IntermediateValue TO Variable, FROM CompositeLiteral TO Variable, loop_with STRING);
"""


def _close_all(result: kuzu.QueryResult | list[kuzu.QueryResult]) -> None:
    if isinstance(result, list):
        for part in result:
            part.close()
    else:
        result.close()


def _escape_string(v: str) -> str:
    """Escape special characters in the given string, such as newlines."""
    # JSON does all the escaping we need, but we'll strip out the surrounding
    # quotes so that the queries do not need to deal with them.
    return json.dumps(v)[1:-1]


def _node_to_dict(node: Node) -> Mapping[str, DatabaseValue]:
    node_dict = {
        k: (_escape_string(v) if isinstance(v, str) else v)
        for k, v in node.model_dump(exclude={"location"}).items()
    }

    return node_dict


def _nodes_to_dicts(nodes: Sequence[Node]) -> Sequence[Mapping[str, DatabaseValue]]:
    nodes_serialised = list(map(_node_to_dict, nodes))
    return nodes_serialised


type EdgeType = tuple[str, str, str]
type EdgeValue = tuple[Node, Node, Edge]


def _edge_to_dict(edge: EdgeValue) -> Mapping[str, DatabaseValue]:
    source, target, edge_value = edge
    edge_serialised = {
        "from": source.node_id,
        "to": target.node_id,
    } | edge_value.model_dump()
    return edge_serialised


def _edges_to_dicts(edges: list[EdgeValue]) -> Sequence[Mapping[str, DatabaseValue]]:
    edges_serialised = list(map(_edge_to_dict, edges))
    return edges_serialised


class DatabaseResultConverter[T](Protocol):
    def __call__(self, result: tuple[DatabaseValue, ...], /) -> T: ...


def _results_to_list[ResultType](
    raw_results: kuzu.QueryResult | list[kuzu.QueryResult],
    result_converter: DatabaseResultConverter[ResultType],
) -> Sequence[ResultType]:
    results: Sequence[ResultType] = []
    if not isinstance(raw_results, list):
        raw_results = [raw_results]

    for raw_result in raw_results:
        while raw_result.has_next():
            results.append(result_converter(tuple(raw_result.get_next())))

    return results


@final
class GraphDatabase:
    def __init__(self, pdg: Graph) -> None:
        self._pdg = pdg
        self._db: kuzu.Database
        self._conn: kuzu.Connection
        self._node_locations: dict[int, NodeLocation]

    def _populate_schema(self) -> None:
        _close_all(self._conn.execute(SCHEMA))

    def _populate_pdg(self) -> None:
        with tempfile.TemporaryDirectory() as d_str:
            d = Path(d_str)
            for node_type, node_file in self._create_node_csvs(d):
                _close_all(
                    self._conn.execute(
                        f'COPY {node_type} FROM "{node_file}" (header=true);'
                    )
                )

            for (
                (source_type, target_type, edge_type),
                edge_file,
            ) in self._create_edge_csvs(d):
                _close_all(
                    self._conn.execute(
                        f'COPY {edge_type} FROM "{edge_file}" (header=true, from="{source_type}", to="{target_type}");'
                    )
                )

        self._populate_node_locations()

    def _create_node_csvs(self, d: Path) -> Iterator[tuple[str, Path]]:
        type_to_nodes = defaultdict[str, list[Node]](list)
        for node in self._pdg.nodes:
            type_to_nodes[node.__class__.__name__].append(node)

        dumped_nodes = {
            node_type: _nodes_to_dicts(nodes)
            for node_type, nodes in type_to_nodes.items()
        }

        for node_type, node_rows in dumped_nodes.items():
            node_file = d / f"{node_type}.csv"
            with node_file.open("w") as f:
                writer = csv.DictWriter(f, fieldnames=node_rows[0].keys())
                writer.writeheader()
                writer.writerows(node_rows)
            yield node_type, node_file

    def _create_edge_csvs(self, d: Path) -> Iterator[tuple[EdgeType, Path]]:
        type_to_edges = defaultdict[EdgeType, list[EdgeValue]](list)
        for source, target, edge in self._pdg.edges:
            dict_key = (
                source.__class__.__name__,
                target.__class__.__name__,
                # prefix with e_ to avoid name clashes with reserved keywords
                "e_" + edge.__class__.__name__,
            )
            type_to_edges[dict_key].append((source, target, edge))

        dumped_edges = {
            edge_type: _edges_to_dicts(edges)
            for edge_type, edges in type_to_edges.items()
        }

        for edge_type, edge_rows in dumped_edges.items():
            (source_type, target_type, edge_type_name) = edge_type
            edge_file = d / f"{source_type}-{edge_type_name}-{target_type}.csv"
            with edge_file.open("w") as f:
                writer = csv.DictWriter(f, fieldnames=edge_rows[0].keys())
                writer.writeheader()
                writer.writerows(edge_rows)
            yield edge_type, edge_file

    def _populate_node_locations(self) -> None:
        self._node_locations = {
            node.node_id: node.location
            for node in self._pdg.nodes
            if node.location is not None
        }

    def __enter__(self) -> Self:
        self._db = kuzu.Database(":memory:")
        self._conn = kuzu.Connection(self._db)

        self._populate_schema()
        self._populate_pdg()

        results = self._conn.execute("MATCH (n1:Task) RETURN n1")
        _close_all(results)

        return self

    def __exit__(self, exc_type: object, exc_val: object, exc_tb: object) -> None:
        self._conn.close()
        self._db.close()

    def query[ResultType](
        self,
        result_converter: DatabaseResultConverter[ResultType],
        query: str,
        parameters: Mapping[str, DatabaseValue] | None = None,
    ) -> Sequence[ResultType]:
        parameters = dict(parameters) if parameters is not None else None
        raw_results = self._conn.execute(query, parameters=parameters)
        results = _results_to_list(raw_results, result_converter)

        _close_all(raw_results)
        return results

    def get_location(self, node_id: int) -> NodeLocation | None:
        return self._node_locations.get(node_id)
