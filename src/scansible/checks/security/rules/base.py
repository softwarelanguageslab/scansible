from __future__ import annotations

from typing import NamedTuple, Any, Sequence

import abc
import json

# from ..db import RedisGraphDatabase


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

    def _create_string_contains_test(self, tokens: Sequence[str], value_accessor: str, type_accessor: str = '') -> str:
        token_queries = [self._create_single_string_contains_test(token, value_accessor) for token in tokens]
        token_query = f'({" OR ".join(token_queries)})'

        if not type_accessor:
            return token_query
        return f'({type_accessor} = "str" AND {token_query})'

    def _create_single_string_contains_test(self, token: str, value_accessor: str) -> str:
        return f'{value_accessor} CONTAINS "{token}"'

    def _create_contained_in_test(self, tokens: Sequence[str], value_accessor: str) -> str:
        token_list = ', '.join(f'"{token}"' for token in tokens)
        return f'({value_accessor} IN [{token_list}])'

    def _create_string_starts_or_ends_with_test(self, tokens: str | Sequence[str], value_accessor: str, type_accessor: str, operator: str) -> str:
        if isinstance(tokens, str):
            tokens = [tokens]

        sw_query = '(' + ' OR '.join(f'{value_accessor} {operator} "{token}"' for token in tokens) + ')'
        if not type_accessor:
            return sw_query
        return f'({type_accessor} = "str" AND {sw_query})'

    def _create_string_startswith_test(self, tokens: str | Sequence[str], value_accessor: str, type_accessor: str = '') -> str:
        return self._create_string_starts_or_ends_with_test(tokens, value_accessor, type_accessor, 'STARTS WITH')

    def _create_string_endswith_test(self, tokens: str | Sequence[str], value_accessor: str, type_accessor: str = '') -> str:
        return self._create_string_starts_or_ends_with_test(tokens, value_accessor, type_accessor, 'ENDS WITH')

    def _create_literal_bool_true_test(self, literal_name: str) -> str:
        return self._create_contained_in_test(['y', 'yes', 'true', 'on', '1', 't', '1.0'], f'toLower(trim(toString({literal_name}.value)))')

    def _create_literal_bool_false_test(self, literal_name: str) -> str:
        return self._create_contained_in_test(['n', 'no', 'false', 'off', '0', 'f', '0.0'], f'toLower(trim(toString({literal_name}.value)))')

    @abc.abstractproperty
    def query(self) -> str:
        raise NotImplementedError('To be implemented by subclass')

    def postprocess_results(self, results: list[tuple[Any, ...]], db: Any) -> list[tuple[str, str, int]]:
        return results  # type: ignore[return-value]

    def run(self, graph_db: Any) -> list[RuleResult]:
        raw_results = graph_db.query(self.query)
        results = []
        for source_location, sink_location, indirection_level in self.postprocess_results(raw_results.result_set, graph_db):
            results.append(RuleResult(self.name, _convert_location(source_location), _convert_location(sink_location), indirection_level))

        return results
