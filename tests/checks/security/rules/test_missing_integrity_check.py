from __future__ import annotations

from typing import TYPE_CHECKING

from functools import partial

from security_helpers import (  # pyright: ignore[reportImplicitRelativeImport]
    make_result,
    run_all_checks,
    stringify,
    temp_import_pb,
    write_pb,
)

from scansible.checks.security.rules.missing_integrity_check import (
    MissingIntegrityCheckRule,
)

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, MissingIntegrityCheckRule.code)


def test_matches_literal_url_on_task(tmp_path: Path) -> None:
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
        results = stringify(MissingIntegrityCheckRule().check(context))

    assert results == [
        _result(
            "`args.url` downloads content without an integrity check",
            "pb.yml:4:19",
            "pb.yml:5:26",
        )
    ]


def test_matches_variable_on_task(tmp_path: Path) -> None:
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
        results = stringify(MissingIntegrityCheckRule().check(context))

    assert results == [
        _result(
            "`args.url` downloads content without an integrity check",
            "pb.yml:6:19",
            "pb.yml:4:27",
        )
    ]


def test_matches_expression_creating_url(tmp_path: Path) -> None:
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
        results = stringify(MissingIntegrityCheckRule().check(context))

    assert results == [
        _result(
            "`args.url` downloads content without an integrity check",
            "pb.yml:6:19",
            "pb.yml:7:26",
        )
    ]


def test_does_not_match_url_with_checksum(tmp_path: Path) -> None:
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
        results = stringify(MissingIntegrityCheckRule().check(context))

    assert not results


def test_does_not_match_non_source_url(tmp_path: Path) -> None:
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
        results = stringify(MissingIntegrityCheckRule().check(context))

    assert not results


def test_glitch_no_integrity_check(tmp_path: Path) -> None:
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
