from __future__ import annotations

from typing import final, override

from .base import Rule


@final
class WeakCryptoAlgorithmRule(Rule):
    description = "Do not use weak cryptographic algorithms like CRC32, MD5, or SHA-1. Use SHA-256 or stronger instead."

    BAD_ALGOS = ("md5", "sha1", "crc32", "crc16", "arcfour")
    BAD_ALGO_REGEX = f"(?i)({'|'.join(BAD_ALGOS)})"

    @property
    @override
    def query(self) -> tuple[str, dict[str, str]]:
        return (
            f"""
            {self._create_query("ScalarLiteral", "value", "")}
            UNION
            {self._create_query("Expression", "expr")}
        """,
            {"bad_algo_regex": self.BAD_ALGO_REGEX},
        )

    def _create_query(
        self, source_type: str, value_prop: str, type_prop: str = ""
    ) -> str:
        value_accessor = f"source.{value_prop}"
        # type_accessor = f"source.{type_prop}" if type_prop else ""
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[:e_Keyword*0..1]->(sink:Task:Variable)
            WHERE regexp_matches({value_accessor}, $bad_algo_regex)
                AND NOT (label(sink) = "Variable" AND (sink)-[:e_Input|e_Keyword]->())
            RETURN source.node_id, sink.node_id
        """
