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

from scansible.checks.security.rules.http_without_ssl_tls import HTTPWithoutSSLTLSRule

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, HTTPWithoutSSLTLSRule.code)


def test_matches_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert results == [
        _result(
            "`args.url` is set to an insecure HTTP URL",
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
                file_url: http://example.com/
              tasks:
                - get_url:
                    url: '{{ file_url }}'
        """,
        pb_path,
    )
    with temp_import_pb(pb_path) as context:
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert results == [
        _result(
            "`args.url` is set to an insecure HTTP URL",
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
                    url: 'http://{{ server }}/test'
        """,
        pb_path,
    )
    with temp_import_pb(pb_path) as context:
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert results == [
        _result(
            "`args.url` is set to an insecure HTTP URL",
            "pb.yml:6:19",
            "pb.yml:7:26",
        )
    ]


def test_matches_transitive_expression_creating_url(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert results == [
        _result(
            "`args.url` is set to an insecure HTTP URL",
            "pb.yml:7:19",
            "pb.yml:5:22",
        )
    ]


def test_does_not_match_localhost(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert not results


def test_does_not_match_localhost_ip(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert not results


def test_does_not_match_localhost_in_expression(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert not results


def test_does_not_match_localhost_with_indirection(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert not results


def test_does_not_match_https(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert not results


def test_matches_only_the_correct_one(tmp_path: Path) -> None:
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
        results = stringify(HTTPWithoutSSLTLSRule().check(context))

    assert results == [
        _result(
            "`args.url` is set to an insecure HTTP URL",
            "pb.yml:10:19",
            "pb.yml:4:22",
        )
    ]


def test_glitch_http_without_tls_ssl(tmp_path: Path) -> None:
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
        make_result(
            HTTPWithoutSSLTLSRule.code,
            "`args.url` is set to an insecure HTTP URL",
            "pb.yml:4:19",
            "pb.yml:6:26",
        )
    ]
