from __future__ import annotations

from .base import Rule


class HardcodedSecretRule(Rule):

    PASSWORD_TOKENS = ('pass', 'pwd', 'auth.*token', 'secret', 'ssh.*key')
    PRIV_KEY_PREFIXES = ('pvt', 'priv')
    PRIV_KEY_SUFFIXES = ('cert', 'key', 'rsa', 'secret', 'ssl')

    @classmethod
    def secret_regexp(cls) -> str:
        priv_key_regex = f'(({"|".join(cls.PRIV_KEY_PREFIXES)}).+({"|".join(cls.PRIV_KEY_SUFFIXES)}))'
        all_tokens = list(cls.PASSWORD_TOKENS) + [priv_key_regex]
        return f'.*({"|".join(all_tokens)}).*'

    @property
    def query(self) -> str:
        return f'''
            {self._construct_query("[arg:KEYWORD]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:DEF|DEFLOOPITEM]->(sink:Variable)", "sink.name")}
        '''

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f'''
            MATCH chain = (source:Literal)-[:DEF|USE|DEFLOOPITEM*0..]->()-{chain_tail}
            WHERE {key_getter} =~ '{self.secret_regexp()}'
                AND source.value <> ''
                AND source.type = 'str'
            RETURN DISTINCT
                source.location as source_location,
                sink.location as sink_location,
                size([x in nodes(chain) where x:Expression]) as indirection_level
        '''
