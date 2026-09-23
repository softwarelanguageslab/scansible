from __future__ import annotations

from typing import final, override

from .base import GraphDBRule, RuleQuery


@final
class DisabledIntegrityCheckRule(GraphDBRule):
    code = "SEC008"
    description = (
        "Do not disable integrity checks, downloaded content could be tampered with"
    )

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
        query = """
            MATCH (source:ScalarLiteral) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[check_key:e_Keyword]->(sink:Task)
            WHERE
                (regexp_matches(check_key.keyword, $check_integrity_flags_regex)
                  AND (NOT regexp_matches(check_key.keyword, $disable_check_integrity_flags_regex))
                  AND regexp_matches(CAST(source.value AS STRING), $literal_bool_false_regex))
                OR
                (regexp_matches(check_key.keyword, $disable_check_integrity_flags_regex)
                  AND regexp_matches(CAST(source.value AS STRING), $literal_bool_true_regex))
            RETURN source.node_id, sink.node_id, check_key.keyword
        """
        params = {
            "check_integrity_flags_regex": self.CHECK_INTEGRITY_FLAGS_REGEX,
            "disable_check_integrity_flags_regex": self.DISABLE_CHECK_INTEGRITY_FLAGS_REGEX,
            "literal_bool_true_regex": self.LITERAL_BOOL_TRUE_REGEX,
            "literal_bool_false_regex": self.LITERAL_BOOL_FALSE_REGEX,
        }
        return query, params

    @override
    def describe(self, label: str) -> str:
        return f"`{label}` disables the integrity check"
