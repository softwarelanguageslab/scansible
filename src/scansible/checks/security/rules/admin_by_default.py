from __future__ import annotations

from typing import final, override

from .base import Rule, RuleQuery


@final
class AdminByDefaultRule(Rule):
    description = (
        "Avoid using admin accounts, as this violates the principle of least privileges"
    )

    #: Token in task keywords that indicate user names or roles.
    USER_ROLE_TOKENS = ("user", "role", "uname", "login", "root", "admin")
    USER_ROLE_REGEX = "|".join(USER_ROLE_TOKENS)

    #: Names that indicate an administrator account is used.
    ADMIN_NAMES = ["admin", "root"]

    @property
    @override
    def query(self) -> RuleQuery:
        query = """
            MATCH (source:ScalarLiteral)-[:e_Def|e_Input|e_DefLoopItem*0..]->()-[arg:e_Keyword]->(sink:Task)
            WHERE regexp_matches(arg.keyword, $user_role_regex) AND source.value IN $admin_name_list
            RETURN source.node_id, sink.node_id
        """
        params = {
            "user_role_regex": self.USER_ROLE_REGEX,
            "admin_name_list": self.ADMIN_NAMES,
        }
        return query, params
