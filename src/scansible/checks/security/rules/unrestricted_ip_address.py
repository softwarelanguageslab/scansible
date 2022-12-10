from __future__ import annotations

from .base import Rule


class UnrestrictedIPAddressRule(Rule):

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
            WHERE source.{value_prop} CONTAINS '0.0.0.0'
                AND (sink:Task OR (sink:Variable AND NOT (sink)-[:USE|KEYWORD]->()))
            RETURN
                source.location as source_location,
                sink.location as sink_location,
                size([x in nodes(chain) where x:Expression]) as indirection_level
        '''
