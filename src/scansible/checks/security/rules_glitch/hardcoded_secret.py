from __future__ import annotations

import itertools

from .base import Rule


class HardcodedSecretRule(Rule):

    PASSWORD_TOKENS = ["pass", "pwd", "password", "passwd", "passno", "pass-no", "pass_no"]
    SECRETS = ["auth_token", "authetication_token","auth-token", "authentication-token",
        "secret", "uuid", "crypt", "certificate", "token", "ssh_key", "md5",
            "rsa", "ssl_content", "ca_content", "ssl-content", "ca-content",
                "ssh_key_content", "ssh-key-content", "ssh_key_public",
                    "ssh-key-public", "ssh_key_private", "ssh-key-private",
                        "ssh_key_public_content", "ssh_key_private_content",
                            "ssh-key-public-content", "ssh-key-private-content", "key", "cert"]

    def create_secret_test(self, key_getter: str) -> str:
        return self._create_string_contains_test(self.PASSWORD_TOKENS + self.SECRETS, key_getter)

    @property
    def query(self) -> str:
        return f'''
            {self._construct_query("[arg:KEYWORD]->(sink:Task)", "arg.keyword")}
            UNION
            {self._construct_query("[:DEF|DEFLOOPITEM]->(sink:Variable)-[:DEF|DEFLOOPITEM|USE*0..]->()-[arg:KEYWORD]->(:Task)", "sink.name")}
        '''

    def _construct_query(self, chain_tail: str, key_getter: str) -> str:
        return f'''
            MATCH chain = (source:Literal)-[:DEF|USE|DEFLOOPITEM*0..]->()-{chain_tail}
            WHERE {self.create_secret_test(key_getter)}
                AND source.value <> '' AND source.type <> 'NoneType'
                AND NOT (source.type <> 'str' AND toString(source.value) CONTAINS "{{{{")
            RETURN {self._query_returns}
        '''
