# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import TYPE_CHECKING

import sys
from contextlib import contextmanager
from functools import partial

import pytest
from loguru import logger

from scansible.checks.base import CheckContext, Finding
from scansible.checks.security import rules
from scansible.checks.security.db import GraphDatabase
from scansible.checks.security.rules.admin_by_default import AdminByDefaultRule
from scansible.checks.security.rules.disabled_integrity_check import (
    DisabledIntegrityCheckRule,
)
from scansible.checks.security.rules.empty_password import EmptyPasswordRule
from scansible.checks.security.rules.hardcoded_secret import HardcodedSecretRule
from scansible.checks.security.rules.http_without_ssl_tls import HTTPWithoutSSLTLSRule
from scansible.checks.security.rules.missing_integrity_check import (
    MissingIntegrityCheckRule,
)
from scansible.checks.security.rules.unrestricted_ip_address import (
    UnrestrictedIPAddressRule,
)
from scansible.checks.security.rules.weak_crypto import WeakCryptoAlgorithmRule
from scansible.pdg import build_pdg

if TYPE_CHECKING:
    from collections.abc import Generator
    from pathlib import Path


@contextmanager
def temp_import_pb(path: Path) -> Generator[CheckContext]:
    logger.remove()
    pdg_ctx = build_pdg(path, [])
    _ = logger.add(sys.stderr, format="{level} {message}", level="DEBUG")
    with GraphDatabase(pdg_ctx.graph) as graph_db:
        yield CheckContext(graph=pdg_ctx.graph, db=graph_db)


def write_pb(content: str, path: Path) -> None:
    _ = path.write_text(content)


#: A `Finding`, but with each `NodeLocation` collapsed down to its
#: `path:line:column` string to avoid deep positioning checks in tests.
type StringifiedResult = tuple[str, str, str, str | None]


def _make_result(
    code: str, summary: str, location: str, hint_location: str | None = None
) -> StringifiedResult:
    return (code, summary, location, hint_location)


def _stringify(results: list[Finding]) -> list[StringifiedResult]:
    return [
        _make_result(
            f.code,
            f.summary,
            str(f.location),
            str(f.hint_location) if f.hint_location is not None else None,
        )
        for f in results
    ]


def run_all_checks(context: CheckContext) -> list[StringifiedResult]:
    results: list[Finding] = []
    for rule in rules.get_all_rules():
        results.extend(rule.check(context))
    return _stringify(results)


def describe_hardcoded_secret_rule() -> None:
    _result = partial(_make_result, HardcodedSecretRule.code)

    def matches_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: test
                  user:
                    name: me
                    password: sekrit
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert results == [
            _result(
                "`args.password` contains a hardcoded secret",
                "pb.yml:4:19",
                "pb.yml:7:31",
            )
        ]

    def matches_variable_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                a_var: sekrit
              tasks:
                - name: test
                  user:
                    name: me
                    password: '{{ a_var }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert results == [
            _result(
                "`args.password` contains a hardcoded secret",
                "pb.yml:6:19",
                "pb.yml:4:24",
            )
        ]

    def matches_2_chain_variable_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                a_var: sekrit
                another_var: '{{ a_var }}'
              tasks:
                - name: test
                  user:
                    name: me
                    password: '{{ another_var }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert results == [
            _result(
                "`args.password` contains a hardcoded secret",
                "pb.yml:7:19",
                "pb.yml:4:24",
            )
        ]

    def matches_variable_name_with_literal(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                secret_password: sekrit
              tasks:
                - debug: msg={{ secret_password }}
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert results == [
            _result(
                "`secret_password` contains a hardcoded secret",
                "pb.yml:4:17",
                "pb.yml:4:34",
            )
        ]

    def matches_indirect_variable_name(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                a_var: sekrit
                secret_password: '{{ a_var }}'
              tasks:
                - debug: msg={{ secret_password }}
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert results == [
            _result(
                "`secret_password` contains a hardcoded secret",
                "pb.yml:5:17",
                "pb.yml:4:24",
            )
        ]

    def does_not_match_update_password_flag_as_literal(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - user:
                    name: me
                    update_password: yes
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert not results

    def does_not_match_update_password_flag_as_expression(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                should_update_password: no
              tasks:
                - user:
                    name: me
                    update_password: '{{ should_update_password }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert not results

    def does_not_match_vault_value(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - user:
                    name: me
                    password: !vault test
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert not results

    def does_not_match_variable_from_inventory(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - user:
                    name: me
                    password: '{{ some_password_likely_in_inventory }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert not results

    def does_not_match_task_key_in_whitelist(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - user:
                    name: me
                    password: '{{ some_password_likely_in_inventory }}'
                    update_password: 'on_create'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HardcodedSecretRule().check(context))

        assert not results


def describe_empty_password_rule() -> None:
    _result = partial(_make_result, EmptyPasswordRule.code)

    def matches_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: test
                  user:
                    name: me
                    password: ''
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(EmptyPasswordRule().check(context))

        assert results == [
            _result(
                "`args.password` is set to an empty password",
                "pb.yml:4:19",
                "pb.yml:7:31",
            )
        ]

    def matches_omit_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: test
                  user:
                    name: me
                    password: omit
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(EmptyPasswordRule().check(context))

        assert results == [
            _result(
                "`args.password` is set to an empty password",
                "pb.yml:4:19",
                "pb.yml:7:31",
            )
        ]

    def matches_null_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: test
                  user:
                    name: me
                    password:
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(EmptyPasswordRule().check(context))

        assert results == [
            _result(
                "`args.password` is set to an empty password",
                "pb.yml:4:19",
            )
        ]

    def matches_variable_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                a_var: ''
              tasks:
                - name: test
                  user:
                    name: me
                    password: '{{ a_var }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(EmptyPasswordRule().check(context))

        assert results == [
            _result(
                "`args.password` is set to an empty password",
                "pb.yml:6:19",
                "pb.yml:4:24",
            )
        ]

    def matches_2_chain_variable_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                a_var: ''
                another_var: '{{ a_var }}'
              tasks:
                - name: test
                  user:
                    name: me
                    password: '{{ another_var }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(EmptyPasswordRule().check(context))

        assert results == [
            _result(
                "`args.password` is set to an empty password",
                "pb.yml:7:19",
                "pb.yml:4:24",
            )
        ]

    def matches_variable_name_with_literal(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                secret_password: ''
              tasks:
                - debug: msg={{ secret_password }}
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(EmptyPasswordRule().check(context))

        assert results == [
            _result(
                "`secret_password` is set to an empty password",
                "pb.yml:4:17",
                "pb.yml:4:34",
            )
        ]

    def matches_indirect_variable_name(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                a_var: ''
                secret_password: '{{ a_var }}'
              tasks:
                - debug: msg={{ secret_password }}
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(EmptyPasswordRule().check(context))

        assert results == [
            _result(
                "`secret_password` is set to an empty password",
                "pb.yml:5:17",
                "pb.yml:4:24",
            )
        ]


def describe_admin_by_default_rule() -> None:
    _result = partial(_make_result, AdminByDefaultRule.code)

    def matches_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - debug: msg=test
                  become_user: admin
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(AdminByDefaultRule().check(context))

        assert results == [
            _result(
                "`become_user` is set to an administrator account",
                "pb.yml:4:19",
                "pb.yml:5:32",
            )
        ]

    def matches_variable_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                user_name: admin
              tasks:
                - debug: msg=test
                  become_user: '{{ user_name }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(AdminByDefaultRule().check(context))

        assert results == [
            _result(
                "`become_user` is set to an administrator account",
                "pb.yml:6:19",
                "pb.yml:4:28",
            )
        ]


def describe_http_without_tls_or_ssl_rule() -> None:
    _result = partial(_make_result, HTTPWithoutSSLTLSRule.code)

    def matches_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: http://example.com
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert results == [
            _result(
                "`args.url` is set to an insecure HTTP URL",
                "pb.yml:4:19",
                "pb.yml:5:26",
            )
        ]

    def matches_variable_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                file_url: http://example.com/
              tasks:
                - get_url:
                    url: '{{ file_url }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert results == [
            _result(
                "`args.url` is set to an insecure HTTP URL",
                "pb.yml:6:19",
                "pb.yml:4:27",
            )
        ]

    def matches_expression_creating_url(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                server: example.com
              tasks:
                - get_url:
                    url: 'http://{{ server }}/test'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert results == [
            _result(
                "`args.url` is set to an insecure HTTP URL",
                "pb.yml:6:19",
                "pb.yml:7:26",
            )
        ]

    def matches_transitive_expression_creating_url(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                server: example.com
                url: 'http://{{ server }}/test'
              tasks:
                - get_url:
                    url: '{{ url }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert results == [
            _result(
                "`args.url` is set to an insecure HTTP URL",
                "pb.yml:7:19",
                "pb.yml:5:22",
            )
        ]

    def does_not_match_localhost(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: http://localhost/test
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert not results

    def does_not_match_localhost_ip(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: http://127.0.0.1/test
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert not results

    def does_not_match_localhost_in_expression(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: 'http://127.0.0.1/{{ path }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert not results

    def does_not_match_localhost_with_indirection(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                server: 'localhost'
                url: 'http://{{ server }}/test'
              tasks:
                - get_url:
                    url: '{{ url }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert not results

    def does_not_match_https(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: 'https://example.com/'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert not results

    def matches_only_the_correct_one(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                url: 'http://{{ server }}/test'
              tasks:
                - get_url:
                    url: '{{ url }}'
                  vars:
                    server: localhost
                - get_url:
                    url: '{{ url }}'
                  vars:
                    server: google.com
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(HTTPWithoutSSLTLSRule().check(context))

        assert results == [
            _result(
                "`args.url` is set to an insecure HTTP URL",
                "pb.yml:10:19",
                "pb.yml:4:22",
            )
        ]


def describe_missing_integrity_check_rule() -> None:
    _result = partial(_make_result, MissingIntegrityCheckRule.code)

    def matches_literal_url_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: https://example.com/source.tar.gz
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(MissingIntegrityCheckRule().check(context))

        assert results == [
            _result(
                "`args.url` downloads content without an integrity check",
                "pb.yml:4:19",
                "pb.yml:5:26",
            )
        ]

    def matches_variable_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                file_url: https://example.com/source.tar.gz
              tasks:
                - get_url:
                    url: '{{ file_url }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(MissingIntegrityCheckRule().check(context))

        assert results == [
            _result(
                "`args.url` downloads content without an integrity check",
                "pb.yml:6:19",
                "pb.yml:4:27",
            )
        ]

    def matches_expression_creating_url(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                server: example.com
              tasks:
                - get_url:
                    url: 'https://{{ server }}/source.tar.gz'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(MissingIntegrityCheckRule().check(context))

        assert results == [
            _result(
                "`args.url` downloads content without an integrity check",
                "pb.yml:6:19",
                "pb.yml:7:26",
            )
        ]

    def does_not_match_url_with_checksum(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: https://example.com/source.tar.gz
                    checksum: test
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(MissingIntegrityCheckRule().check(context))

        assert not results

    def does_not_match_non_source_url(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: 'http://127.0.0.1/test'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(MissingIntegrityCheckRule().check(context))

        assert not results


def describe_disabled_integrity_check_rule() -> None:
    _result = partial(_make_result, DisabledIntegrityCheckRule.code)

    def matches_disabled_gpgcheck(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - apt:
                    name: test
                    gpgcheck: no
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(DisabledIntegrityCheckRule().check(context))

        assert results == [
            _result(
                "`args.gpgcheck` disables the integrity check",
                "pb.yml:4:19",
                "pb.yml:6:31",
            )
        ]

    def matches_inverted_disabled_gpgcheck(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - yum:
                    name: test
                    disable_gpg_check: yes
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(DisabledIntegrityCheckRule().check(context))

        assert results == [
            _result(
                "`args.disable_gpg_check` disables the integrity check",
                "pb.yml:4:19",
                "pb.yml:6:40",
            )
        ]

    def matches_disabled_gpgcheck_indirectly(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                do_gpg: no
              tasks:
                - apt:
                    name: test
                    gpgcheck: '{{ do_gpg }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(DisabledIntegrityCheckRule().check(context))

        assert results == [
            _result(
                "`args.gpgcheck` disables the integrity check",
                "pb.yml:6:19",
                "pb.yml:4:25",
            )
        ]

    def does_not_match_enabled_gpgcheck(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - apt:
                    name: test
                    gpgcheck: yes
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(DisabledIntegrityCheckRule().check(context))

        assert not results

    def does_not_match_inverted_enabled_gpgcheck(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - apt:
                    name: test
                    disablegpgcheck: no
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(DisabledIntegrityCheckRule().check(context))

        assert not results


def describe_unrestricted_ip_address_rule() -> None:
    _result = partial(_make_result, UnrestrictedIPAddressRule.code)

    def matches_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - test:
                    bind: 0.0.0.0
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(UnrestrictedIPAddressRule().check(context))

        assert results == [
            _result(
                "`args.bind` binds to an unrestricted IP address",
                "pb.yml:4:19",
                "pb.yml:5:27",
            )
        ]

    def matches_indirect_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                bind_address: 0.0.0.0
              tasks:
                - test:
                    bind: '{{ bind_address }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(UnrestrictedIPAddressRule().check(context))

        assert results == [
            _result(
                "`args.bind` binds to an unrestricted IP address",
                "pb.yml:6:19",
                "pb.yml:4:31",
            )
        ]

    def does_not_match_10_0_0_0(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                bind_address: 10.0.0.0
              tasks:
                - test:
                    bind: '{{ bind_address }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(UnrestrictedIPAddressRule().check(context))

        assert not results


def describe_weak_crypto_rule() -> None:
    _result = partial(_make_result, WeakCryptoAlgorithmRule.code)

    def matches_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - get_url:
                    url: https://example.com/source.tar.gz
                    checksum: 'md5:123456'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(WeakCryptoAlgorithmRule().check(context))

        assert results == [
            _result(
                "`args.checksum` uses a weak cryptographic algorithm",
                "pb.yml:4:19",
                "pb.yml:6:31",
            )
        ]

    def matches_indirect_literal_on_task(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              vars:
                file_checksum: 'md5:123456'
              tasks:
                - get_url:
                    url: https://example.com/source.tar.gz
                    checksum: '{{ file_checksum }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(WeakCryptoAlgorithmRule().check(context))

        assert results == [
            _result(
                "`args.checksum` uses a weak cryptographic algorithm",
                "pb.yml:6:19",
                "pb.yml:4:32",
            )
        ]

    def matches_usage_in_expressions(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - user:
                    name: me
                    password: '{{ some_pass | password_hash("md5") }}'
        """,
            pb_path,
        )
        with temp_import_pb(pb_path) as context:
            results = _stringify(WeakCryptoAlgorithmRule().check(context))

        assert results == [
            _result(
                "`args.password` uses a weak cryptographic algorithm",
                "pb.yml:4:19",
                "pb.yml:6:31",
            )
        ]


def describe_glitch_test_cases() -> None:
    def admin_by_default(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: Install serverspec
                  become_user: root
                  command: gem install serverspec
        """,
            pb_path,
        )

        with temp_import_pb(pb_path) as context:
            results = run_all_checks(context)

        assert results == [
            _make_result(
                AdminByDefaultRule.code,
                "`become_user` is set to an administrator account",
                "pb.yml:4:19",
                "pb.yml:5:32",
            )
        ]

    @pytest.mark.xfail(reason="nested key in dict literal")
    def empty_password(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: login, get SID
                  uri:
                    url: "https://{{ hostvars[inventory_hostname|regex_replace('ansible-1', 'checkpoint_mgmt')]['private_ip'] }}/web_api/login"
                    method: POST
                    body:
                      user: "{{ admin }}"
                      password:
                    body_format: json
                    validate_certs: false
                  register: login_data
                  until: (login_data.status == 200) and (login_data.json is defined)
                  retries: 30
                  delay: 10
        """,
            pb_path,
        )

        with temp_import_pb(pb_path) as context:
            results = run_all_checks(context)

        assert results == [
            _make_result(
                EmptyPasswordRule.code,
                "`args.password` is set to an empty password",
                "pb.yml:4:19",
            )
        ]

    @pytest.mark.xfail(reason="nested key in dict literal")
    def hardcoded_secret(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: login, get SID
                  uri:
                    url: "https://{{ hostvars[inventory_hostname|regex_replace('ansible-1', 'checkpoint_mgmt')]['private_ip'] }}/web_api/login"
                    method: POST
                    body:
                      user: test
                      password: '123'
                    body_format: json
                    validate_certs: false
                  register: login_data
                  until: (login_data.status == 200) and (login_data.json is defined)
                  retries: 30
                  delay: 10
        """,
            pb_path,
        )

        with temp_import_pb(pb_path) as context:
            results = run_all_checks(context)

        assert results == [
            _make_result(
                HardcodedSecretRule.code,
                "`args.password` contains a hardcoded secret",
                "pb.yml:4:19",
                "pb.yml:10:33",
            )
        ]

    def http_without_tls_ssl(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: login, get SID
                  uri:
                    url: "http://{{ hostvars[inventory_hostname|regex_replace('ansible-1', 'checkpoint_mgmt')]['private_ip'] }}/web_api/login"
                    method: POST
                    body:
                      user: "{{ user }}"
                      password: "{{ password }}"
                    body_format: json
                    validate_certs: false
                  register: login_data
                  until: (login_data.status == 200) and (login_data.json is defined)
                  retries: 30
                  delay: 10

        """,
            pb_path,
        )

        with temp_import_pb(pb_path) as context:
            results = run_all_checks(context)

        assert results == [
            _make_result(
                HTTPWithoutSSLTLSRule.code,
                "`args.url` is set to an insecure HTTP URL",
                "pb.yml:4:19",
                "pb.yml:6:26",
            )
        ]

    def no_integrity_check(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: Check for credentials file for registry auth
                  stat:
                    path: "{{ oreg_auth_credentials_path }}"
                    get_checksum: false
                    get_attributes: false
                    get_mime: false
                  when: oreg_auth_user is defined
                  register: node_oreg_auth_credentials_stat

        """,
            pb_path,
        )

        with temp_import_pb(pb_path) as context:
            results = run_all_checks(context)

        # False positive
        assert not results

    @pytest.mark.xfail(reason="unsupported literal type")
    def unrestricted_ip_address(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: enable live-migraiton in nova
                  ini_file: dest={{ nova_conf }} section=DEFAULT option={{ item.key }} value={{ item.value }} create=yes
                  notify: restart nova-compute
                  with_dict:
                    live_migration_flag: "VIR_MIGRATE_UNDEFINE_SOURCE,VIR_MIGRATE_PEER2PEER,VIR_MIGRATE_LIVE"
                    vncserver_listen: "0.0.0.0"

        """,
            pb_path,
        )

        with temp_import_pb(pb_path) as context:
            results = run_all_checks(context)

        assert results == [
            _make_result(
                UnrestrictedIPAddressRule.code,
                "`args.bind` binds to an unrestricted IP address",
                "pb.yml:4:19",
                "pb.yml:6:39",
            )
        ]

    def weak_crypto(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_pb(
            """
            - hosts: localhost
              tasks:
                - name: Generate the {{ db_username }} MD5 password
                  set_fact:
                    db_password_md5: "md5{{ (db_password~db_username) | hash('md5') }}"

                - name: Create the {{ db_username }} database user ({{ database }})
                  shell: su - postgres -c "psql -c \"CREATE ROLE {{ db_username }} ENCRYPTED PASSWORD
                    '{{ db_password_md5 }}' NOSUPERUSER NOCREATEDB NOCREATEROLE INHERIT LOGIN;\""
                  args:
                    warn: false
                  register: createuser_results
                  ignore_errors: true

        """,
            pb_path,
        )

        with temp_import_pb(pb_path) as context:
            results = run_all_checks(context)

        assert sorted(results) == sorted(
            [
                _make_result(
                    WeakCryptoAlgorithmRule.code,
                    "`args._raw_params` uses a weak cryptographic algorithm",
                    "pb.yml:8:19",
                    "pb.yml:6:38",
                ),
                # Due to the whole shell command expression containing "md5" as a substring.
                _make_result(
                    WeakCryptoAlgorithmRule.code,
                    "`args._raw_params` uses a weak cryptographic algorithm",
                    "pb.yml:8:19",
                    "pb.yml:9:26",
                ),
            ]
        )
