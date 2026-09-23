from __future__ import annotations

from typing import final, override

from .base import GraphDBRule, RuleQuery


@final
class HTTPWithoutSSLTLSRule(GraphDBRule):
    code = "SEC004"
    description = "Always use SSL/TLS to connect over HTTP, i.e., use HTTPS"

    #: Regular expression to identify http:// URLs.
    HTTP_REGEX = "^http://"

    #: IPs and domain names that are allowed with http:// URLs.
    IP_WHITELIST = ("localhost", "127.0.0.1")
    IP_WHITELIST_REGEX = f"^(http://)?{'|'.join(IP_WHITELIST)}"

    @property
    @override
    def query(self) -> RuleQuery:
        # Split queries into task keyword/variable name since the returned label differs for each
        # Flows of an insecure URL to a task argument
        query_literal_task = self._construct_query("ScalarLiteral", "value")
        query_expr_task = self._construct_query("Expression", "expr")
        # Flows of an insecure URL terminating in an unused variable
        query_literal_var = self._construct_query(
            "ScalarLiteral", "value", to_variable=True
        )
        query_expr_var = self._construct_query("Expression", "expr", to_variable=True)

        query = f"""
            {query_literal_task}
            UNION
            {query_literal_var}
            UNION
            {query_expr_task}
            UNION
            {query_expr_var}
        """
        params = {
            "http_regex": self.HTTP_REGEX,
            "ip_whitelist_regex": self.IP_WHITELIST_REGEX,
        }
        return query, params

    def _construct_query(
        self, source_type: str, value_prop: str, *, to_variable: bool = False
    ) -> str:
        value_accessor = f"source.{value_prop}"
        ignore_localhost_source = ""
        if source_type == "Expression":
            # Ignore expressions that have an incoming node with localhost
            ignore_localhost_source = """
                AND (NOT EXISTS {
                    MATCH (server_source:ScalarLiteral) -[:e_Def|e_Input|e_DefLoopItem*0..]->(source)
                    WHERE regexp_matches(server_source.value, $ip_whitelist_regex)
                })
            """
        if to_variable:
            return f"""
                MATCH (source:{source_type}) -[:e_Def|e_Input|e_DefLoopItem*0..]->(sink:Variable)
                WHERE regexp_matches({value_accessor}, $http_regex)
                    AND (NOT regexp_matches({value_accessor}, $ip_whitelist_regex))
                    AND (NOT (sink)-[:e_Input|e_Keyword]->())
                    {ignore_localhost_source}
                RETURN source.node_id, sink.node_id, sink.name
            """
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_Input|e_DefLoopItem*0..]->()-[kw:e_Keyword]->(sink:Task)
            WHERE regexp_matches({value_accessor}, $http_regex)
                AND (NOT regexp_matches({value_accessor}, $ip_whitelist_regex))
                {ignore_localhost_source}
            RETURN source.node_id, sink.node_id, kw.keyword
        """

    @override
    def describe(self, label: str) -> str:
        return f"`{label}` is set to an insecure HTTP URL"
