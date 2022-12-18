from __future__ import annotations

from ..rules.base import Rule


class WeakCryptoAlgorithmRule(Rule):

    BAD_ALGOS = ('md5', 'sha1')

    def create_bad_algo_test(self, value_accessor: str, type_accessor: str = '') -> str:
        return self._create_string_contains_test(self.BAD_ALGOS, f'toLower(toString({value_accessor}))', type_accessor)

    @property
    def query(self) -> str:
        return f'''
            {self._create_query("Literal", "value", "")}
            UNION
            {self._create_query("Expression", "expr")}
        '''

    def _create_query(self, source_type: str, value_prop: str, type_prop: str = '') -> str:
        value_accessor = f'source.{value_prop}'
        type_accessor = f'source.{type_prop}' if type_prop else ''
        return f'''
            MATCH chain = (source:{source_type}) -[:DEF|USE|DEFLOOPITEM*0..]->()-[check_arg:KEYWORD*0..1]->(sink)
            WHERE {self.create_bad_algo_test(value_accessor, type_accessor)}
                AND (sink:Task OR (sink:Variable AND NOT (sink)-[:USE|KEYWORD]->()))
            RETURN {self._query_returns}
        '''
