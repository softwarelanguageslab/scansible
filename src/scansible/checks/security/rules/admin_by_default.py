from __future__ import annotations

from .base import Rule


class AdminByDefaultRule(Rule):

    USER_ROLE_TOKENS = ('user.*', 'role', 'uname', 'login.*', 'root', 'admin', 'owner.*')
    ADMIN_NAMES = ('admin', 'root')

    @classmethod
    def username_regexp(cls) -> str:
        return f'.*({"|".join(cls.USER_ROLE_TOKENS)}).*'

    @classmethod
    def admin_name_regexp(cls) -> str:
        return f'({"|".join(cls.ADMIN_NAMES)})'

    @property
    def query(self) -> str:
        return f'''
            MATCH chain = (source:Literal)-[:DEF|USE|DEFLOOPITEM*0..]->()-[arg:KEYWORD]->(sink:Task)
            WHERE source.value =~ '{self.admin_name_regexp()}'
                AND arg.keyword =~ '{self.username_regexp()}'
            RETURN DISTINCT
                source.location as source_location,
                sink.location as sink_location,
                size([x in nodes(chain) where x:Expression]) as indirection_level
        '''

