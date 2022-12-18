from __future__ import annotations

from ..rules.base import Rule


class HTTPWithoutSSLTLSRule(Rule):

    def create_http_test(self, key_getter: str, type_getter: str) -> str:
        return self._create_string_startswith_test('http:', key_getter, type_getter)

    @property
    def query(self) -> str:
        return f'''
            {self._create_query("Literal", "source.value", "source.type")}
            UNION
            {self._create_query("Expression", "source.expr", "")}
        '''

    def _create_query(self, source_type: str, value_getter: str, type_getter: str) -> str:
        return f'''
            MATCH chain = (source:{source_type}) -[:DEF|USE|DEFLOOPITEM*0..]->()-[:KEYWORD*0..1]->(sink)
            WHERE {self.create_http_test(value_getter, type_getter)}
                AND (sink:Task OR (sink:Variable AND NOT (sink)-[:USE|KEYWORD]->()))
            RETURN {self._query_returns}
        '''


