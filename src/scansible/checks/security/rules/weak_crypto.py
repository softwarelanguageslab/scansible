from __future__ import annotations

from .base import Rule


class WeakCryptoAlgorithmRule(Rule):

    BAD_ALGOS = ('md5', 'sha1', 'crc32', 'crc16', 'arcfour')

    @classmethod
    def bad_algos_regexp(cls) -> str:
        return '.*(' + '|'.join(cls.BAD_ALGOS) + ').*'

    @property
    def query(self) -> str:
        return f'''
            {self._create_query("Literal", "value")}
            UNION
            {self._create_query("Expression", "expr")}
        '''

    def _create_query(self, source_type: str, value_prop: str) -> str:
        return f'''
            MATCH chain = (source:{source_type}) -[:DEF|USE|DEFLOOPITEM*0..]->()-[:KEYWORD*0..1]->(sink)
            WHERE toLower(toString(source.{value_prop})) =~ '{self.bad_algos_regexp()}'
                AND (sink:Task OR (sink:Variable AND NOT (sink)-[:USE|KEYWORD]->()))
            RETURN
                source.location as source_location,
                sink.location as sink_location,
                size([x in nodes(chain) where x:Expression]) as indirection_level
        '''
