from __future__ import annotations

from typing import final, override

from .base import Rule


@final
class UnrestrictedIPAddressRule(Rule):
    description = "Do not bind to the 0.0.0.0 address, as this exposes the service to the entire Internet"

    BAD_IP_REGEX = r"\b0\.0\.0\.0"

    @property
    @override
    def query(self) -> tuple[str, dict[str, str]]:
        return (
            f"""
            {self._create_query("ScalarLiteral", "value", "type")}
            UNION
            {self._create_query("Expression", "expr")}
        """,
            {"bad_ip_regex": self.BAD_IP_REGEX},
        )

    def _create_query(
        self, source_type: str, value_prop: str, type_prop: str = ""
    ) -> str:
        value_accessor = f"source.{value_prop}"
        # type_accessor = f"source.{type_prop}" if type_prop else ""
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[:e_Keyword*0..1]->(sink:Task:Variable)
            WHERE regexp_matches({value_accessor}, $bad_ip_regex)
                AND (NOT (label(sink) = "Variable" AND (sink)-[:e_Input|e_Keyword]->()))
            RETURN source.node_id, sink.node_id
        """
