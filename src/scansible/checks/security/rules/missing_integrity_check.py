from __future__ import annotations

from typing import final, override

from .base import GraphDBRule, RuleQuery


@final
class MissingIntegrityCheckRule(GraphDBRule):
    code = "SEC005"
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

    @property
    @override
    def query(self) -> RuleQuery:
        # Downloads where the URL is provided as a literal
        query_literal_url = self._create_query("ScalarLiteral", "value")
        # Downloads where the URL is constructed through an expression
        query_expression_url = self._create_query("Expression", "expr")

        query = f"""
            {query_literal_url}
            UNION
            {query_expression_url}
        """
        params = {
            "checksum_argument_regex": self.CHECKSUM_ARGUMENT_REGEX,
            "download_regex": self.DOWNLOAD_REGEX,
        }
        return query, params

    def _create_query(self, source_type: str, value_prop: str) -> str:
        value_prop = f"source.{value_prop}"
        return f"""
            MATCH (source:{source_type}) -[:e_Def|e_DefLoopItem|e_Input*0..]->()-[dl:e_Keyword]->(sink:Task)
            WHERE regexp_matches({value_prop}, $download_regex)
                AND NOT EXISTS {{ MATCH ()-[e:e_Keyword]->(sink) WHERE regexp_matches(e.keyword, $checksum_argument_regex) }}
            RETURN source.node_id, sink.node_id, dl.keyword
        """

    @override
    def describe(self, label: str) -> str:
        return f"`{label}` downloads content without an integrity check"
