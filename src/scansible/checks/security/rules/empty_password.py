from __future__ import annotations

from .base import Rule


class EmptyPasswordRule(Rule):

    PASSWORD_TOKENS = ("pass", "pwd")

    def create_password_test(self, key_getter: str) -> str:
        return self._create_string_contains_test(self.PASSWORD_TOKENS, key_getter)

    @property
    def query(self) -> str:
        return f"""
            {self._construct_query("[arg:KEYWORD]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:DEF|DEFLOOPITEM]->(sink:Variable)-[:DEF|DEFLOOPITEM|INPUT*0..]->()-[:KEYWORD]->(:Task)", "sink.name")}
        """

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f"""
            MATCH chain = (source:ScalarLiteral)-[:DEF|INPUT|DEFLOOPITEM*0..]->()-{chain_tail}
            WHERE {self.create_password_test(key_getter)}
                AND ((source.type = 'str' AND source.value = '' or source.value = 'omit')
                    OR source.type = 'NoneType')
            {self._query_returns}
        """
