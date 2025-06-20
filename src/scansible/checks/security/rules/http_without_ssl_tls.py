from __future__ import annotations

from typing import final, override

from .base import Rule, RuleQuery


@final
class HTTPWithoutSSLTLSRule(Rule):
    description = "Always use SSL/TLS to connect over HTTP, i.e., use HTTPS"

    #: Regular expression to identify http:// URLs.
    HTTP_REGEX = "^http://"

    #: IPs and domain names that are allowed with http:// URLs.
    IP_WHITELIST = ("localhost", "127.0.0.1")
    IP_WHITELIST_REGEX = f"^(http://)?{'|'.join(IP_WHITELIST)}"

    @property
    @override
    def query(self) -> RuleQuery:
        query = """
            MATCH (source:ScalarLiteral) -[:e_Def|e_Input|e_DefLoopItem*0..]->()-[:e_Keyword*0..1]->(sink:Task:Variable)
            WHERE regexp_matches(source.value, $http_regex)
                AND (NOT regexp_matches(source.value, $ip_whitelist_regex))
                AND (NOT (label(sink) = "Variable" AND (sink)-[:e_Input|e_Keyword]->()))
            RETURN source.node_id, sink.node_id

            UNION

            MATCH (source:Expression) -[:e_Def|e_Input|e_DefLoopItem*0..]->()-[:e_Keyword*0..1]->(sink:Task:Variable)
            WHERE regexp_matches(source.expr, $http_regex)
                AND (NOT regexp_matches(source.expr, $ip_whitelist_regex))
                AND (NOT (label(sink) = "Variable" AND (sink)-[:e_Input|e_Keyword]->()))
                // Ignore expressions that have an incoming node with localhost
                AND (NOT EXISTS {
                    MATCH (server_source:ScalarLiteral) -[:e_Def|e_Input|e_DefLoopItem*0..]->(source)
                    WHERE regexp_matches(server_source.value, $ip_whitelist_regex)
                })
            RETURN source.node_id, sink.node_id
        """
        params = {
            "http_regex": self.HTTP_REGEX,
            "ip_whitelist_regex": self.IP_WHITELIST_REGEX,
        }
        return query, params
