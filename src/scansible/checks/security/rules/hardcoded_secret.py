from __future__ import annotations

import itertools

from .base import Rule


class HardcodedSecretRule(Rule):

    PASSWORD_TOKENS = (
        ("pass",),
        ("pwd",),
        ("token",),
        ("secret",),
        ("ssh", "key"),
        ("ca", "content"),
        ("ssl", "content"),
    )
    PRIV_KEY_PREFIXES = ("pvt", "priv")
    PRIV_KEY_SUFFIXES = ("cert", "key", "rsa", "secret", "ssl")

    KEYWORD_WHITELIST = ("update", "generate")

    def create_secret_test(self, key_getter: str) -> str:
        password_test_parts = [
            f'({" AND ".join(self._create_single_string_contains_test(token, key_getter) for token in token_sequences)})'
            for token_sequences in self.PASSWORD_TOKENS
        ]
        password_test = f'({" OR ".join(password_test_parts)})'
        priv_key_suffixes_test = self._create_string_contains_test(
            self.PRIV_KEY_SUFFIXES, key_getter
        )
        priv_key_prefixes_test = self._create_string_contains_test(
            self.PRIV_KEY_PREFIXES, key_getter
        )
        priv_key_test = f"(({priv_key_prefixes_test}) AND ({priv_key_suffixes_test}))"

        return f"({password_test} OR {priv_key_test})"

    def create_secret_whitelist_test(self, key_getter: str) -> str:
        return f"(NOT {self._create_string_contains_test(self.KEYWORD_WHITELIST, key_getter)})"

    @property
    def query(self) -> str:
        return f"""
            {self._construct_query("[arg:KEYWORD]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:DEF|DEFLOOPITEM]->(sink:Variable)-[:DEF|DEFLOOPITEM|USE*0..]->()-[arg:KEYWORD]->(:Task)", "sink.name")}
        """

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f"""
            MATCH chain = (source:Literal)-[:DEF|USE|DEFLOOPITEM*0..]->()-{chain_tail}
            WHERE {self.create_secret_test(key_getter)}
                AND {self.create_secret_whitelist_test(key_getter)}
                AND source.value <> ''
                AND source.type = 'str'
            {self._query_returns}
        """
