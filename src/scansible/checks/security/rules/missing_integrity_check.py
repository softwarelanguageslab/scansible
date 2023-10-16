from __future__ import annotations

from .base import Rule


class MissingIntegrityCheckRule(Rule):

    SOURCE_EXTS = (
        "dmg",
        "rpm",
        "tgz",
        "zip",
        "tar",
        "tbz",
        "iso",
        "rar",
        "gzip",
        "deb",
        "sh",
        "run",
        "bin",
        "gz",
        "bzip2",
        "bz",
        "xz",
    )
    DOWNLOAD_PREFIXES = ("http:", "https:", "ftp:", "www.")
    CHECKSUM_TOKENS = ("checksum", "cksum")
    CHECK_INTEGRITY_FLAGS = ("gpg_check", "gpgcheck", "check_sha", "checksha")
    DISABLE_CHECK_INTEGRITY_FLAGS = (
        "disable_gpg_check",
        "disablegpgcheck",
        "disable_gpgcheck",
    )

    def create_download_test(self, value_getter: str, type_getter: str = "") -> str:
        download_query = f"(({self._create_string_startswith_test(self.DOWNLOAD_PREFIXES, value_getter)}) AND ({self._create_string_endswith_test(self.SOURCE_EXTS, value_getter)}))"
        if not type_getter:
            return download_query
        return f'({type_getter} = "str" AND {download_query})'

    def create_checksum_test(self, value_getter: str) -> str:
        return self._create_string_contains_test(self.CHECKSUM_TOKENS, value_getter)

    def create_check_integrity_flags_test(self, value_getter: str) -> str:
        return self._create_string_contains_test(
            self.CHECK_INTEGRITY_FLAGS, value_getter
        )

    def create_disable_check_integrity_flags_test(self, value_getter: str) -> str:
        return self._create_string_contains_test(
            self.DISABLE_CHECK_INTEGRITY_FLAGS, value_getter
        )

    @property
    def query(self) -> str:
        # Repeated similar queries for the flags are due to some Neo4j weirdness.
        return f"""
            {self._create_query("ScalarLiteral", "value", "type")}
            UNION
            {self._create_query("Expression", "expr")}
            UNION
            MATCH chain = (source:ScalarLiteral) -[:DEF|INPUT|DEFLOOPITEM*0..]->()-[check_key:KEYWORD]->(sink:Task)
            WHERE
                ({self.create_check_integrity_flags_test("check_key.keyword")} AND {self._create_literal_bool_false_test("source")})
                OR
                ({self.create_disable_check_integrity_flags_test("check_key.keyword")} AND {self._create_literal_bool_true_test("source")})
            {self._query_returns}
        """

    def _create_query(
        self, source_type: str, value_prop: str, type_prop: str = ""
    ) -> str:
        if type_prop:
            type_prop = f"source.{type_prop}"
        value_prop = f"source.{value_prop}"
        return f"""
            MATCH chain = (source:{source_type}) -[:DEF|INPUT|DEFLOOPITEM*0..]->()-[:KEYWORD]->(sink:Task)
            WHERE {self.create_download_test(value_prop, type_prop)}
                AND {" AND ".join(f'(NOT ()-[:KEYWORD {{ keyword: "args.{check_kw}" }}]->(sink))' for check_kw in self.CHECKSUM_TOKENS)}
            {self._query_returns}
        """
