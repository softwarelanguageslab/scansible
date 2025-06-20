from __future__ import annotations

from typing import final, override

from .base import Rule, RuleQuery


@final
class UnrestrictedIPAddressRule(Rule):
    description = "Do not bind to the 0.0.0.0 address, as this exposes the service to the entire Internet"

    #: Regular expression to identify bad IP addresses.
    BAD_IP_REGEX = r"\b0\.0\.0\.0"

    @property
    @override
    def query(self) -> RuleQuery:
        #: Query for bad IP contained in a literal
        query_literal = self._create_query("ScalarLiteral", "value")
        #: Query for bad IP contained in an expression
        query_expression = self._create_query("Expression", "expr")

        query = f"""
            {query_literal}
            UNION
            {query_expression}
        """
        params = {"bad_ip_regex": self.BAD_IP_REGEX}
        return query, params

    def _create_query(self, source_type: str, value_prop: str) -> str:
        value_accessor = f"source.{value_prop}"
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[:e_Keyword*0..1]->(sink:Task:Variable)
            WHERE regexp_matches({value_accessor}, $bad_ip_regex)
                AND (NOT (label(sink) = "Variable" AND (sink)-[:e_Input|e_Keyword]->()))
            RETURN source.node_id, sink.node_id
        """
