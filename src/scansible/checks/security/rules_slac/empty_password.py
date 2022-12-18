from __future__ import annotations

from ..rules.base import Rule


class EmptyPasswordRule(Rule):

    PASSWORD_TOKENS = ["pass", "pwd", "password"]

    def create_password_test(self, key_getter: str) -> str:
        return self._create_string_contains_test(self.PASSWORD_TOKENS, key_getter)

    @property
    def query(self) -> str:
        return f'''
            {self._construct_query("[arg:KEYWORD]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:DEF|DEFLOOPITEM]->(sink:Variable)-[:DEF|DEFLOOPITEM|USE*0..]->()-[:KEYWORD]->(:Task)", "sink.name")}
        '''

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f'''
            MATCH chain = (source:Literal)-[:DEF|USE|DEFLOOPITEM*0..]->()-{chain_tail}
            WHERE {self.create_password_test(key_getter)}
                AND ((source.type = 'str' AND source.value = '')
                    OR source.type = 'NoneType')
            RETURN {self._query_returns}
        '''
