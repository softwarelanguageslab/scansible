from __future__ import annotations

from typing import final, override

from .base import Rule


@final
class HardcodedSecretRule(Rule):
    description = "Hardcoded secrets can compromise security when the source code falls into the wrong hands"

    TOKEN_REGEXES = (
        "pass",
        "pwd",
        "token",
        "secret",
        "ssh.*key",
        "key.*ssh",
        "(ca|ssl).*content",
        "content.*(ca|ssl)",
    )
    PRIV_KEY_PREFIXES = ("pvt", "priv")
    PRIV_KEY_SUFFIXES = ("cert", "key", "rsa", "secret", "ssl")

    PRIV_KEY_REGEX = f"({'|'.join(PRIV_KEY_PREFIXES)}).*({'|'.join(PRIV_KEY_SUFFIXES)})"
    SECRET_REGEX = f"{'|'.join(TOKEN_REGEXES)}|{PRIV_KEY_REGEX}"

    KEYWORD_WHITELIST = ("update", "generate")
    KEYWORD_WHITELIST_REGEX = "|".join(KEYWORD_WHITELIST)

    @property
    @override
    def query(self) -> tuple[str, dict[str, str]]:
        return (
            f"""
            {self._construct_query("[arg:e_Keyword]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:e_Def|e_DefLoopItem]->(sink:Variable)-[:e_Def|e_DefLoopItem|e_Input*0..]->()-[arg:e_Keyword]->(:Task)", "sink.name")}
        """,
            {
                "secret_regex": self.SECRET_REGEX,
                "keyword_whitelist_regex": self.KEYWORD_WHITELIST_REGEX,
            },
        )

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f"""
            MATCH (source:ScalarLiteral)-[:e_Def|e_Input|e_DefLoopItem*0..]->()-{chain_tail}
            WHERE regexp_matches({key_getter}, $secret_regex)
                AND (NOT regexp_matches({key_getter}, $keyword_whitelist_regex))
                AND source.value <> ''
                AND source.type = 'str'
            RETURN source.node_id, sink.node_id
        """
