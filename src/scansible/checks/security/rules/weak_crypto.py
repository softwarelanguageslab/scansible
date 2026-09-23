from __future__ import annotations

from typing import final, override

from .base import GraphDBRule, RuleQuery


@final
class WeakCryptoAlgorithmRule(GraphDBRule):
    code = "SEC007"
    description = "Do not use weak cryptographic algorithms like `CRC32`, `MD5`, or `SHA-1`. Use `SHA-256` or stronger instead."

    #: Tokens that indicate bad crypto algorithms being used.
    BAD_ALGOS = ("md5", "sha1", "crc32", "crc16", "arcfour")
    BAD_ALGO_REGEX = f"(?i)({'|'.join(BAD_ALGOS)})"

    @property
    @override
    def query(self) -> RuleQuery:
        # Split queries into task keyword/variable name since the returned label differs for each
        query_literal_task = self._create_query("ScalarLiteral", "value")
        query_expr_task = self._create_query("Expression", "expr")
        query_literal_var = self._create_query(
            "ScalarLiteral", "value", to_variable=True
        )
        query_expr_var = self._create_query("Expression", "expr", to_variable=True)

        query = f"""
            {query_literal_task}
            UNION
            {query_literal_var}
            UNION
            {query_expr_task}
            UNION
            {query_expr_var}
        """
        params = {"bad_algo_regex": self.BAD_ALGO_REGEX}
        return query, params

    def _create_query(
        self, source_type: str, value_prop: str, *, to_variable: bool = False
    ) -> str:
        value_accessor = f"source.{value_prop}"
        if to_variable:
            return f"""
                MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->(sink:Variable)
                WHERE regexp_matches({value_accessor}, $bad_algo_regex)
                    AND NOT (sink)-[:e_Input|e_Keyword]->()
                RETURN source.node_id, sink.node_id, sink.name
            """
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[kw:e_Keyword]->(sink:Task)
            WHERE regexp_matches({value_accessor}, $bad_algo_regex)
            RETURN source.node_id, sink.node_id, kw.keyword
        """

    @override
    def describe(self, label: str) -> str:
        return f"`{label}` uses a weak cryptographic algorithm"
