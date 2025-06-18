from __future__ import annotations

from typing import final, override

from .base import Rule


@final
class EmptyPasswordRule(Rule):
    description = "Never use empty passwords, these are easy to crack"

    PASSWORD_TOKENS = ("pass", "pwd")
    PASSWORD_REGEX = "|".join(PASSWORD_TOKENS)

    @property
    @override
    def query(self) -> tuple[str, dict[str, str]]:
        return (
            f"""
            {self._construct_query("[arg:e_Keyword]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:e_Def|e_DefLoopItem]->(sink:Variable)-[:e_Def|e_DefLoopItem|e_Input*0..]->()-[:e_Keyword]->(:Task)", "sink.name")}
        """,
            {"password_regex": self.PASSWORD_REGEX},
        )

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f"""
            MATCH (source:ScalarLiteral)-[:e_Def|e_Input|e_DefLoopItem*0..]->()-{chain_tail}
            WHERE regexp_matches({key_getter}, $password_regex)
                AND (source.type = 'NoneType' OR (source.type = 'str' AND (source.value = 'omit' OR source.value IS NULL)))
            RETURN source.node_id, sink.node_id
        """
