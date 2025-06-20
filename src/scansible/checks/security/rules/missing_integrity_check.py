from __future__ import annotations

from typing import final, override

from .base import Rule, RuleQuery


@final
class MissingIntegrityCheckRule(Rule):
    description = "The integrity of source code needs to be checked with cryptographic hashes after downloading"

    #: File extensions that indicate downloads of source code files.
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
    #: String prefixes that indicate URLs being downloaded.
    DOWNLOAD_PREFIXES = ("http:", "https:", "ftp:", "www.")
    DOWNLOAD_REGEX = f"^({'|'.join(DOWNLOAD_PREFIXES)}).+({'|'.join(SOURCE_EXTS)})$"

    #: Argument substrings that indicate a target checksum is provided.
    CHECKSUM_TOKENS = ("checksum", "cksum")
    CHECKSUM_ARGUMENT_REGEX = rf"^args\..*({'|'.join(CHECKSUM_TOKENS)})"

    #: Argument substrings that enable integrity checks.
    CHECK_INTEGRITY_FLAGS = ("gpg_?check", "check_?sha")
    #: Argument substrings that disable integrity checks.
    DISABLE_CHECK_INTEGRITY_FLAGS = ("disable_?gpg_?check",)

    CHECK_INTEGRITY_FLAGS_REGEX = rf"^args\..*({'|'.join(CHECK_INTEGRITY_FLAGS)})"
    DISABLE_CHECK_INTEGRITY_FLAGS_REGEX = (
        rf"^args\..*({'|'.join(DISABLE_CHECK_INTEGRITY_FLAGS)})"
    )

    #: Boolean literal True values
    LITERAL_BOOL_TRUE_VALUES = ("y", "yes", "true", "on", "1", "t", "1.0")
    LITERAL_BOOL_TRUE_REGEX = rf"(?i)^\s*({'|'.join(LITERAL_BOOL_TRUE_VALUES)})\s*$"
    #: Boolean literal False values
    LITERAL_BOOL_FALSE_VALUES = ("n", "no", "false", "off", "0", "f", "0.0")
    LITERAL_BOOL_FALSE_REGEX = rf"(?i)^\s*({'|'.join(LITERAL_BOOL_FALSE_VALUES)})\s*$"

    @property
    @override
    def query(self) -> RuleQuery:
        # Downloads where the URL is provided as a literal
        query_literal_url = self._create_query("ScalarLiteral", "value")
        # Downloads where the URL is constructed through an expression
        query_expression_url = self._create_query("Expression", "expr")
        # Tasks with arguments that explicitly disable integrity checks
        query_disabled_check = """
            MATCH (source:ScalarLiteral) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[check_key:e_Keyword]->(sink:Task)
            WHERE
                (regexp_matches(check_key.keyword, $check_integrity_flags_regex)
                  AND (NOT regexp_matches(check_key.keyword, $disable_check_integrity_flags_regex))
                  AND regexp_matches(CAST(source.value AS STRING), $literal_bool_false_regex))
                OR
                (regexp_matches(check_key.keyword, $disable_check_integrity_flags_regex)
                  AND regexp_matches(CAST(source.value AS STRING), $literal_bool_true_regex))
            RETURN source.node_id, sink.node_id
        """

        query = f"""
            {query_literal_url}
            UNION
            {query_expression_url}
            UNION
            {query_disabled_check}
        """
        params = {
            "checksum_argument_regex": self.CHECKSUM_ARGUMENT_REGEX,
            "download_regex": self.DOWNLOAD_REGEX,
            "check_integrity_flags_regex": self.CHECK_INTEGRITY_FLAGS_REGEX,
            "disable_check_integrity_flags_regex": self.DISABLE_CHECK_INTEGRITY_FLAGS_REGEX,
            "literal_bool_true_regex": self.LITERAL_BOOL_TRUE_REGEX,
            "literal_bool_false_regex": self.LITERAL_BOOL_FALSE_REGEX,
        }
        return query, params

    def _create_query(self, source_type: str, value_prop: str) -> str:
        value_prop = f"source.{value_prop}"
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[:e_Keyword]->(sink:Task)
            WHERE regexp_matches({value_prop}, $download_regex)
                AND NOT EXISTS {{ MATCH ()-[e:e_Keyword]->(sink) WHERE regexp_matches(e.keyword, $checksum_argument_regex) }}
            RETURN source.node_id, sink.node_id
        """
