from __future__ import annotations

from .base import Rule


class EmptyPasswordRule(Rule):

    PASSWORD_TOKENS = ('pass', 'pwd')

    @classmethod
    def password_regexp(cls) -> str:
        return f'.*({"|".join(cls.PASSWORD_TOKENS)}).*'

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
            WHERE {key_getter} =~ '{self.password_regexp()}'
                AND source.value = ''
                AND source.type = 'str'
            RETURN DISTINCT
                source.location as source_location,
                sink.location as sink_location,
                size([x in nodes(chain) where x:Expression]) as indirection_level
        '''

