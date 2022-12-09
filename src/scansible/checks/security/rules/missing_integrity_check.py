from __future__ import annotations

from .base import Rule


class MissingIntegrityCheckRule(Rule):

    SOURCE_EXTS = ('dmg', 'rpm', 'tgz', 'zip', 'tar', 'tbz', 'iso', 'rar', 'gzip', 'deb', 'sh', 'run', 'bin', 'gz', 'bzip2', 'bz', 'xz')
    DOWNLOAD_PREFIXES = ('http:', 'https:', 'ftp:', 'www\\\\.')
    CHECKSUM_TOKENS = ('checksum', 'cksum')
    CHECK_INTEGRITY_FLAGS = ('gpg_?check', 'check_?sha')


    @classmethod
    def download_regexp(cls) -> str:
        return f'({"|".join(cls.DOWNLOAD_PREFIXES)}).*\\\\.({"|".join(cls.SOURCE_EXTS)})$'

    @classmethod
    def checksum_regexp(cls) -> str:
        return f'.*({"|".join(cls.CHECKSUM_TOKENS)}).*'

    @classmethod
    def check_flags_regexp(cls) -> str:
        return f'.*({"|".join(cls.CHECK_INTEGRITY_FLAGS)}).*'

    @property
    def query(self) -> str:
        return f'''
            {self._create_query("Literal", "value")}
            UNION
            {self._create_query("Expression", "expr")}
            UNION
            MATCH chain = (source:Literal) -[:DEF|USE|DEFLOOPITEM*0..]->()-[check_key:KEYWORD]->(sink:Task)
            WHERE check_key.keyword =~ '{self.check_flags_regexp()}'
                AND ((source.type = 'str' AND source.value = 'no')
                    OR (source.type = 'bool' AND NOT source.value))
            RETURN
                sink.location as source_location,
                sink.location as sink_location,
                size([x in nodes(chain) where x:Expression]) as indirection_level
        '''

    def _create_query(self, source_type: str, value_prop: str) -> str:
        return f'''
            MATCH chain = (source:{source_type}) -[:DEF|USE|DEFLOOPITEM*0..]->()-[:KEYWORD]->(sink:Task)
            WHERE source.{value_prop} =~ '{self.download_regexp()}'
                AND NOT EXISTS {{
                    MATCH ()-[check_key:KEYWORD]->(sink)
                    WHERE check_key.keyword =~ '{self.checksum_regexp()}'
                }}
            RETURN
                source.location as source_location,
                sink.location as sink_location,
                size([x in nodes(chain) where x:Expression]) as indirection_level
        '''
