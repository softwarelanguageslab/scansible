from __future__ import annotations

from typing import final, override

from .base import Rule, RuleQuery


@final
class HardcodedSecretRule(Rule):
    description = "Hardcoded secrets can compromise security when the source code falls into the wrong hands"

    #: Substrings in variable or argument names that indicate secrets.
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

    #: Substrings in variable or argument names that indicate private keys: Prefixes
    PRIV_KEY_PREFIXES = ("pvt", "priv")
    #: Substrings in variable or argument names that indicate private keys: Suffixes
    PRIV_KEY_SUFFIXES = ("cert", "key", "rsa", "secret", "ssl")

    PRIV_KEY_REGEX = f"({'|'.join(PRIV_KEY_PREFIXES)}).*({'|'.join(PRIV_KEY_SUFFIXES)})"
    SECRET_REGEX = f"{'|'.join(TOKEN_REGEXES)}|{PRIV_KEY_REGEX}"

    #: Tokens in variable or argument names that indicate non-secrets when combined with
    #: a secret token (e.g., update_password: True).
    KEYWORD_WHITELIST = ("update", "generate")
    KEYWORD_WHITELIST_REGEX = "|".join(KEYWORD_WHITELIST)

    @property
    @override
    def query(self) -> RuleQuery:
        # Flows of hardcoded literal to task where secret is identified using task argument name
        query_task_arg = self._construct_query(
            "[arg:e_Keyword]->(sink:Task)", "arg.keyword"
        )
        # Flows of hardcoded literal to task where secret is identified using name of an intermediate variable
        query_var_name = self._construct_query(
            "[:e_Def|e_DefLoopItem]->(sink:Variable)-[:e_Def|e_DefLoopItem|e_Input*0..]->()-[arg:e_Keyword]->(:Task)",
            "sink.name",
        )

        query = f"""
            {query_task_arg}
            UNION
            {query_var_name}
        """
        params = {
            "secret_regex": self.SECRET_REGEX,
            "keyword_whitelist_regex": self.KEYWORD_WHITELIST_REGEX,
        }
        return query, params

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f"""
            MATCH (source:ScalarLiteral)-[:e_Def|e_Input|e_DefLoopItem*0..]->()-{chain_tail}
            WHERE regexp_matches({key_getter}, $secret_regex)
                AND (NOT regexp_matches({key_getter}, $keyword_whitelist_regex))
                AND source.value <> ''
                AND source.type = 'str'
            RETURN source.node_id, sink.node_id
        """
