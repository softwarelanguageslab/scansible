from __future__ import annotations

from typing import final, override

from .base import Rule, RuleQuery


@final
class EmptyPasswordRule(Rule):
    description = "Never use empty passwords, these are easy to crack"

    # Variable or argument name tokens that indicate a password.
    PASSWORD_TOKENS = ("pass", "pwd")
    PASSWORD_REGEX = "|".join(PASSWORD_TOKENS)

    @property
    @override
    def query(self) -> RuleQuery:
        # Flows of empty password to task where password is identified using task argument name
        query_task_arg = self._construct_query(
            "[arg:e_Keyword]->(sink:Task)", "arg.keyword"
        )
        # Flows of empty password to task where password is identified using name of an intermediate variable
        query_var_name = self._construct_query(
            "[:e_Def|e_DefLoopItem]->(sink:Variable)-[:e_Def|e_DefLoopItem|e_Input*0..]->()-[:e_Keyword]->(:Task)",
            "sink.name",
        )

        query = f"""
            {query_task_arg}
            UNION
            {query_var_name}
        """
        params = {"password_regex": self.PASSWORD_REGEX}
        return query, params

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f"""
            MATCH (source:ScalarLiteral)-[:e_Def|e_Input|e_DefLoopItem*0..]->()-{chain_tail}
            WHERE regexp_matches({key_getter}, $password_regex)
                AND (source.type = 'NoneType' OR (source.type = 'str' AND (source.value = 'omit' OR source.value IS NULL)))
            RETURN source.node_id, sink.node_id
        """
