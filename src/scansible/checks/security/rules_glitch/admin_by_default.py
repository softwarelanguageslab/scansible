from __future__ import annotations

from .base import Rule


class AdminByDefaultRule(Rule):

    USER_ROLE_TOKENS = ('root', 'user', "uname", "username", "user-name", "user_name", "owner-name", "owner_name", "admin", "login", "userid", "loginid")
    ADMIN_NAMES = ('admin', 'root')

    @property
    def username_test(self) -> str:
        return self._create_string_contains_test(self.USER_ROLE_TOKENS, 'arg.keyword')

    @property
    def admin_name_test(self) -> str:
        return self._create_contained_in_test(self.ADMIN_NAMES, 'source.value')

    @property
    def query(self) -> str:
        return f'''
            MATCH chain = (source:Literal)-[:DEF|USE|DEFLOOPITEM*0..]->()-[arg:KEYWORD]->(sink:Task)
            WHERE
                {self.username_test}
                AND
                {self.admin_name_test}
                AND NOT (source.type <> 'str' AND toString(source.value) CONTAINS "{{{{")
            RETURN {self._query_returns}
        '''

