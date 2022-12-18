from __future__ import annotations

from ..rules.base import Rule


class HardcodedSecretRule(Rule):

    PASSWORD_TOKENS = ["pass", "pwd", "password"]
    PRIV_KEY_PREFIXES = ('pvt', 'priv')
    PRIV_KEY_SUFFIXES = ('cert', 'key', 'rsa', 'secret', 'ssl')

    def create_secret_test(self, key_getter: str) -> str:
        password_tests = [
            '(' + ' AND '.join(self._create_single_string_contains_test(token, key_getter) for token in token_sequences) + ')'
            for token_sequences in self.PASSWORD_TOKENS
        ]
        priv_key_suffixes_test = ' OR '.join(self._create_single_string_contains_test(priv_key_suffix, key_getter) for priv_key_suffix in self.PRIV_KEY_SUFFIXES)
        priv_key_tests = [
            f'({self._create_single_string_contains_test(priv_key_prefix, key_getter)} AND ({priv_key_suffixes_test}))'
            for priv_key_prefix in self.PRIV_KEY_PREFIXES
        ]

        return '(' + ' OR '.join(password_tests + priv_key_tests) + ')'

    @property
    def query(self) -> str:
        return f'''
            {self._construct_query("[arg:KEYWORD]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:DEF|DEFLOOPITEM]->(sink:Variable)-[:DEF|DEFLOOPITEM|USE*0..]->()-[arg:KEYWORD]->(:Task)", "sink.name")}
        '''

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f'''
            MATCH chain = (source:Literal)-[:DEF|USE|DEFLOOPITEM*0..]->()-{chain_tail}
            WHERE {self.create_secret_test(key_getter)}
                AND source.value <> '' AND source.type <> 'NoneType'
            RETURN {self._query_returns}
        '''
