from __future__ import annotations

from ..rules.base import Rule


class MissingIntegrityCheckRule(Rule):
    SOURCE_EXTS = [
        "iso",
        "tar",
        "tar.gz",
        "tar.bzip2",
        "zip",
        "rar",
        "gzip",
        "gzip2",
        "deb",
        "rpm",
        "sh",
        "run",
        "bin",
    ]
    DOWNLOAD_PREFIXES = ("http", "https", "www.")
    CHECKSUM_TOKENS = ("gpg", "checksum")

    def create_download_test(self, value_getter: str, type_getter: str = "") -> str:
        download_query = f"(({self._create_string_startswith_test(self.DOWNLOAD_PREFIXES, value_getter)}) AND ({self._create_string_endswith_test(self.SOURCE_EXTS, value_getter)}))"
        if not type_getter:
            return download_query
        return f'({type_getter} = "str" AND {download_query})'

    def create_checksum_test(self, value_getter: str) -> str:
        return self._create_string_contains_test(self.CHECKSUM_TOKENS, value_getter)

    @property
    def query(self) -> str:
        # Repeated similar queries for the flags are due to some Neo4j weirdness.
        return f"""
            {self._create_query("Literal", "value", "type")}
            UNION
            {self._create_query("Expression", "expr")}
            UNION
            MATCH chain = (source:Literal) -[:DEF|USE|DEFLOOPITEM*0..]->()-[check_key:KEYWORD]->(sink:Task)
            WHERE
                ({self.create_checksum_test("check_key.keyword")} AND (toLower(toString(source.value)) = "no" OR toLower(toString(source.value)) = "false"))
            {self._query_returns}
        """

    def _create_query(
        self, source_type: str, value_prop: str, type_prop: str = ""
    ) -> str:
        if type_prop:
            type_prop = f"source.{type_prop}"
        value_prop = f"source.{value_prop}"
        return f"""
            MATCH chain = (source:{source_type}) -[:DEF|USE|DEFLOOPITEM*0..]->()-[:KEYWORD]->(sink:Task)
            WHERE {self.create_download_test(value_prop, type_prop)}
                AND {" AND ".join(f'(NOT ()-[:KEYWORD {{ keyword: "args.{check_kw}" }}]->(sink))' for check_kw in self.CHECKSUM_TOKENS)}
            {self._query_returns}
        """
