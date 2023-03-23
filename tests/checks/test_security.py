from __future__ import annotations

from typing import Any, Generator

import os
from contextlib import contextmanager
from pathlib import Path

import pytest

from scansible.checks.security import rules
from scansible.checks.security.db import RedisGraphDatabase
from scansible.checks.security.rules.base import RuleResult
from scansible.representations.pdg import extract_pdg
from scansible.representations.pdg.io.neo4j import dump_graph as pdg_to_neo4j


@pytest.fixture(scope="module")
def db_instance() -> Generator[RedisGraphDatabase, None, None]:
    yield RedisGraphDatabase("localhost")


@contextmanager
def temp_import_pb(db: RedisGraphDatabase, path: Path) -> Generator[Any, None, None]:  # type: ignore[misc]
    pdg_ctx = extract_pdg(path, "test", "test", [])
    query = pdg_to_neo4j(pdg_ctx.graph)
    print(query)
    with db.temporary_graph("test@test", query) as graph:
        yield graph


def write_pb(content: str, path: Path) -> None:
    path.write_text(content)


def run_all_checks(db: RedisGraphDatabase) -> list[RuleResult]:
    results = []
    for rule in rules.get_all_rules():
        results.extend(rule.run(db))
    return results


def describe_hardcoded_secret_rule() -> None:
    def matches_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert results == [
            RuleResult("HardcodedSecret", f"{pb_path}:7:31", f"{pb_path}:4:19", 0)
        ]

    def matches_variable_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert results == [
            RuleResult("HardcodedSecret", f"{pb_path}:4:24", f"{pb_path}:6:19", 1)
        ]

    def matches_2_chain_variable_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert results == [
            RuleResult("HardcodedSecret", f"{pb_path}:4:24", f"{pb_path}:7:19", 2)
        ]

    def matches_variable_name_with_literal(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert results == [
            RuleResult("HardcodedSecret", f"{pb_path}:4:34", f"{pb_path}:4:17", 1)
        ]

    def matches_indirect_variable_name(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert results == [
            RuleResult("HardcodedSecret", f"{pb_path}:4:24", f"{pb_path}:5:17", 2)
        ]

    def does_not_match_update_password_flag_as_literal(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert not results

    def does_not_match_update_password_flag_as_expression(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert not results

    def does_not_match_vault_value(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert not results

    def does_not_match_variable_from_inventory(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert not results

    def does_not_match_task_key_in_whitelist(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HardcodedSecretRule().run(graph_db)

        assert not results


def describe_empty_password_rule() -> None:
    def matches_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.EmptyPasswordRule().run(graph_db)

        assert results == [
            RuleResult("EmptyPassword", f"{pb_path}:7:31", f"{pb_path}:4:19", 0)
        ]

    def matches_null_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.EmptyPasswordRule().run(graph_db)

        assert results == [
            RuleResult("EmptyPassword", f"{pb_path}:4:19", f"{pb_path}:4:19", 0)
        ]

    def matches_variable_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.EmptyPasswordRule().run(graph_db)

        assert results == [
            RuleResult("EmptyPassword", f"{pb_path}:4:24", f"{pb_path}:6:19", 1)
        ]

    def matches_2_chain_variable_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.EmptyPasswordRule().run(graph_db)

        assert results == [
            RuleResult("EmptyPassword", f"{pb_path}:4:24", f"{pb_path}:7:19", 2)
        ]

    def matches_variable_name_with_literal(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.EmptyPasswordRule().run(graph_db)

        assert results == [
            RuleResult("EmptyPassword", f"{pb_path}:4:34", f"{pb_path}:4:17", 1)
        ]

    def matches_indirect_variable_name(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.EmptyPasswordRule().run(graph_db)

        assert results == [
            RuleResult("EmptyPassword", f"{pb_path}:4:24", f"{pb_path}:5:17", 2)
        ]


def describe_admin_by_default_rule() -> None:
    def matches_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.AdminByDefaultRule().run(graph_db)

        assert results == [
            RuleResult("AdminByDefault", f"{pb_path}:5:32", f"{pb_path}:4:19", 0)
        ]

    def matches_variable_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.AdminByDefaultRule().run(graph_db)

        assert results == [
            RuleResult("AdminByDefault", f"{pb_path}:4:28", f"{pb_path}:6:19", 1)
        ]


def describe_http_without_tls_or_ssl_rule() -> None:
    def matches_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert results == [
            RuleResult("HTTPWithoutSSLTLS", f"{pb_path}:5:26", f"{pb_path}:4:19", 0)
        ]

    def matches_variable_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert results == [
            RuleResult("HTTPWithoutSSLTLS", f"{pb_path}:4:27", f"{pb_path}:6:19", 1)
        ]

    def matches_expression_creating_url(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert results == [
            RuleResult("HTTPWithoutSSLTLS", f"{pb_path}:7:26", f"{pb_path}:6:19", 1)
        ]

    def matches_transitive_expression_creating_url(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert results == [
            RuleResult("HTTPWithoutSSLTLS", f"{pb_path}:5:22", f"{pb_path}:7:19", 2)
        ]

    def does_not_match_localhost(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert not results

    def does_not_match_localhost_ip(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert not results

    def does_not_match_localhost_in_expression(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert not results

    def does_not_match_localhost_with_indirection(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert not results

    def does_not_match_https(db_instance: RedisGraphDatabase, tmp_path: Path) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert not results

    def matches_only_the_correct_one(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.HTTPWithoutSSLTLSRule().run(graph_db)

        assert results == [
            RuleResult("HTTPWithoutSSLTLS", f"{pb_path}:4:22", f"{pb_path}:10:19", 2)
        ]


def describe_missing_integrity_check_rule() -> None:
    def matches_literal_url_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert results == [
            RuleResult("MissingIntegrityCheck", f"{pb_path}:5:26", f"{pb_path}:4:19", 0)
        ]

    def matches_variable_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert results == [
            RuleResult("MissingIntegrityCheck", f"{pb_path}:4:27", f"{pb_path}:6:19", 1)
        ]

    def matches_expression_creating_url(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert results == [
            RuleResult("MissingIntegrityCheck", f"{pb_path}:7:26", f"{pb_path}:6:19", 1)
        ]

    def matches_disabled_gpgcheck(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert results == [
            RuleResult("MissingIntegrityCheck", f"{pb_path}:4:19", f"{pb_path}:4:19", 0)
        ]

    def matches_inverted_disabled_gpgcheck(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert results == [
            RuleResult("MissingIntegrityCheck", f"{pb_path}:4:19", f"{pb_path}:4:19", 0)
        ]

    def matches_disabled_gpgcheck_indirectly(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert results == [
            RuleResult("MissingIntegrityCheck", f"{pb_path}:4:17", f"{pb_path}:6:19", 1)
        ]

    def does_not_match_enabled_gpgcheck(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert not results

    def does_not_match_url_with_checksum(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert not results

    def does_not_match_non_source_url(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.MissingIntegrityCheckRule().run(graph_db)

        assert not results


def describe_unrestricted_ip_address_rule() -> None:
    def matches_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.UnrestrictedIPAddressRule().run(graph_db)

        assert results == [
            RuleResult("UnrestrictedIPAddress", f"{pb_path}:5:27", f"{pb_path}:4:19", 0)
        ]

    def matches_indirect_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.UnrestrictedIPAddressRule().run(graph_db)

        assert results == [
            RuleResult("UnrestrictedIPAddress", f"{pb_path}:4:31", f"{pb_path}:6:19", 1)
        ]


def describe_weak_crypto_rule() -> None:
    def matches_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.WeakCryptoAlgorithmRule().run(graph_db)

        assert results == [
            RuleResult("WeakCryptoAlgorithm", f"{pb_path}:6:31", f"{pb_path}:4:19", 0)
        ]

    def matches_indirect_literal_on_task(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.WeakCryptoAlgorithmRule().run(graph_db)

        assert results == [
            RuleResult("WeakCryptoAlgorithm", f"{pb_path}:4:32", f"{pb_path}:6:19", 1)
        ]

    def matches_usage_in_expressions(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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
        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = rules.WeakCryptoAlgorithmRule().run(graph_db)

        assert results == [
            RuleResult("WeakCryptoAlgorithm", f"{pb_path}:6:31", f"{pb_path}:4:19", 1)
        ]


def describe_glitch_test_cases() -> None:
    def admin_by_default(db_instance: RedisGraphDatabase, tmp_path: Path) -> None:
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

        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = run_all_checks(graph_db)

        assert results == [
            RuleResult("AdminByDefault", f"{pb_path}:5:32", f"{pb_path}:4:19", 0)
        ]

    @pytest.mark.xfail(reason="nested key in dict literal")
    def empty_password(db_instance: RedisGraphDatabase, tmp_path: Path) -> None:
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

        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = run_all_checks(graph_db)

        assert results == [
            RuleResult("EmptyPassword", f"{pb_path}:4:19", f"{pb_path}:4:19", 0)
        ]

    @pytest.mark.xfail(reason="nested key in dict literal")
    def hardcoded_secret(db_instance: RedisGraphDatabase, tmp_path: Path) -> None:
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

        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = run_all_checks(graph_db)

        assert results == [
            RuleResult("HardcodedSecret", f"{pb_path}:10:33", f"{pb_path}:4:19", 0)
        ]

    def http_without_tls_ssl(db_instance: RedisGraphDatabase, tmp_path: Path) -> None:
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

        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = run_all_checks(graph_db)

        assert results == [
            RuleResult("HTTPWithoutSSLTLS", f"{pb_path}:6:26", f"{pb_path}:4:19", 1)
        ]

    def no_integrity_check(db_instance: RedisGraphDatabase, tmp_path: Path) -> None:
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

        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = run_all_checks(graph_db)

        # False positive
        assert not results

    @pytest.mark.xfail(reason="unsupported literal type")
    def unrestricted_ip_address(
        db_instance: RedisGraphDatabase, tmp_path: Path
    ) -> None:
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

        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = run_all_checks(graph_db)

        assert results == [
            RuleResult("UnrestrictedIPAddress", f"{pb_path}:6:39", f"{pb_path}:4:19", 1)
        ]

    def weak_crypto(db_instance: RedisGraphDatabase, tmp_path: Path) -> None:
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

        with temp_import_pb(db_instance, pb_path) as graph_db:
            results = run_all_checks(graph_db)

        assert results == [
            RuleResult("WeakCryptoAlgorithm", f"{pb_path}:6:38", f"{pb_path}:8:19", 2),
            RuleResult("WeakCryptoAlgorithm", f"{pb_path}:8:19", f"{pb_path}:8:19", 1),
        ]
