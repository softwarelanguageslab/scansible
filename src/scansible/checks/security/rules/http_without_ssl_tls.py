from __future__ import annotations

from typing import Any

from .base import Rule


class HTTPWithoutSSLTLSRule(Rule):
    IP_WHITELIST = ("localhost", "127.0.0.1")

    def create_http_test(self, key_getter: str, type_getter: str) -> str:
        return self._create_string_startswith_test("http://", key_getter, type_getter)

    def create_localhost_test(self, key_getter: str, type_getter: str) -> str:
        whitelist_tokens: list[str] = []
        for ip in self.IP_WHITELIST:
            whitelist_tokens.extend([ip, f"http://{ip}"])

        return self._create_string_startswith_test(
            whitelist_tokens, key_getter, type_getter
        )

    @property
    def query(self) -> str:
        return f"""
            {self._create_query("ScalarLiteral", "source.value", "source.type")}
            UNION
            {self._create_query("Expression", "source.expr", "")}
        """

    def _create_query(
        self, source_type: str, value_getter: str, type_getter: str
    ) -> str:
        return f"""
            MATCH chain = (source:{source_type}) -[:DEF|INPUT|DEFLOOPITEM*0..]->()-[:KEYWORD*0..1]->(sink)
            WHERE {self.create_http_test(value_getter, type_getter)}
                AND (NOT ({self.create_localhost_test(value_getter, type_getter)}))
                AND (sink:Task OR (sink:Variable AND NOT (sink)-[:INPUT|KEYWORD]->()))
            {self._create_query_returns(["source"], [])}
        """

    def postprocess_results(
        self, results: list[tuple[Any, ...]], db: Any
    ) -> list[tuple[str, str, int]]:
        # Postprocess to remove any results where the source expression node has another incoming node with localhost
        new_results: list[tuple[str, str, int]] = []
        for source, source_loc, sink_loc, indirection_level in results:
            if "Expression" not in source.labels:
                new_results.append((source_loc, sink_loc, indirection_level))
                continue

            subresult = db.query(
                f"""
                MATCH (server_source:ScalarLiteral) -[:DEF|INPUT|DEFLOOPITEM*0..]->({{ node_id: {source.properties["node_id"] }}})
                WHERE {self.create_localhost_test('server_source.value', 'server_source.type')}
                RETURN server_source
            """
            )
            if subresult.result_set:
                # This expression has an incoming literal with localhost => Not a smell, discard.
                continue

            new_results.append((source_loc, sink_loc, indirection_level))

        return new_results
