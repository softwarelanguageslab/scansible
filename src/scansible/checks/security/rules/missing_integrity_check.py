from __future__ import annotations

from typing import final, override

from .base import Rule


@final
class MissingIntegrityCheckRule(Rule):
    description = "The integrity of source code needs to be checked with cryptographic hashes after downloading"

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
    DOWNLOAD_REGEX = f"^({'|'.join(DOWNLOAD_PREFIXES)}).+({'|'.join(SOURCE_EXTS)})$"

    CHECKSUM_TOKENS = ("checksum", "cksum")
    CHECKSUM_ARGUMENT_REGEX = rf"^args\..*({'|'.join(CHECKSUM_TOKENS)})"

    CHECK_INTEGRITY_FLAGS = ("gpg_check", "gpgcheck", "check_sha", "checksha")
    CHECK_INTEGRITY_FLAGS_REGEX = rf"^args\..*({'|'.join(CHECK_INTEGRITY_FLAGS)})"
    DISABLE_CHECK_INTEGRITY_FLAGS = (
        "disable_gpg_check",
        "disablegpgcheck",
        "disable_gpgcheck",
    )
    DISABLE_CHECK_INTEGRITY_FLAGS_REGEX = (
        rf"^args\..*({'|'.join(DISABLE_CHECK_INTEGRITY_FLAGS)})"
    )

    LITERAL_BOOL_TRUE_VALUES = ("y", "yes", "true", "on", "1", "t", "1.0")
    LITERAL_BOOL_TRUE_REGEX = rf"(?i)^\s*({'|'.join(LITERAL_BOOL_TRUE_VALUES)})\s*$"
    LITERAL_BOOL_FALSE_VALUES = ("n", "no", "false", "off", "0", "f", "0.0")
    LITERAL_BOOL_FALSE_REGEX = rf"(?i)^\s*({'|'.join(LITERAL_BOOL_FALSE_VALUES)})\s*$"

    @property
    @override
    def query(self) -> tuple[str, dict[str, str]]:
        # Repeated similar queries for the flags are due to some Neo4j weirdness.
        return (
            f"""
            {self._create_query("ScalarLiteral", "value", "type")}
            UNION
            {self._create_query("Expression", "expr")}
            UNION
            MATCH (source:ScalarLiteral) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[check_key:e_Keyword]->(sink:Task)
            WHERE
                (regexp_matches(check_key.keyword, $check_integrity_flags_regex) AND regexp_matches(CAST(source.value AS STRING), $literal_bool_false_regex))
                OR
                (regexp_matches(check_key.keyword, $disable_check_integrity_flags_regex) AND regexp_matches(CAST(source.value AS STRING), $literal_bool_true_regex))
            RETURN source.node_id, sink.node_id
        """,
            {
                "checksum_argument_regex": self.CHECKSUM_ARGUMENT_REGEX,
                "download_regex": self.DOWNLOAD_REGEX,
                "check_integrity_flags_regex": self.CHECK_INTEGRITY_FLAGS_REGEX,
                "disable_check_integrity_flags_regex": self.DISABLE_CHECK_INTEGRITY_FLAGS_REGEX,
                "literal_bool_true_regex": self.LITERAL_BOOL_TRUE_REGEX,
                "literal_bool_false_regex": self.LITERAL_BOOL_FALSE_REGEX,
            },
        )

    def _create_query(
        self, source_type: str, value_prop: str, type_prop: str = ""
    ) -> str:
        if type_prop:
            type_prop = f"source.{type_prop}"
        value_prop = f"source.{value_prop}"
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[:e_Keyword]->(sink:Task)
            WHERE regexp_matches({value_prop}, $download_regex)
                AND NOT EXISTS {{ MATCH ()-[e:e_Keyword]->(sink) WHERE regexp_matches(e.keyword, $checksum_argument_regex) }}
            RETURN source.node_id, sink.node_id
        """
