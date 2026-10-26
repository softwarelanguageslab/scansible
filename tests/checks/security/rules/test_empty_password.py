from __future__ import annotations

from typing import TYPE_CHECKING

from functools import partial

import pytest
from security_helpers import (  # pyright: ignore[reportImplicitRelativeImport]
    make_result,
    run_all_checks,
    stringify,
    temp_import_pb,
    write_pb,
)

from scansible.checks.security.rules.empty_password import EmptyPasswordRule

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, EmptyPasswordRule.code)


def test_matches_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(EmptyPasswordRule().check(context))

    assert results == [
        _result(
            "`args.password` is set to an empty password",
            "pb.yml:4:19",
            "pb.yml:7:31",
        )
    ]


def test_matches_omit_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(EmptyPasswordRule().check(context))

    assert results == [
        _result(
            "`args.password` is set to an empty password",
            "pb.yml:4:19",
            "pb.yml:7:31",
        )
    ]


def test_matches_null_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(EmptyPasswordRule().check(context))

    assert results == [
        _result(
            "`args.password` is set to an empty password",
            "pb.yml:4:19",
        )
    ]


def test_matches_variable_on_task(tmp_path: Path) -> None:
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
        results = stringify(EmptyPasswordRule().check(context))

    assert results == [
        _result(
            "`args.password` is set to an empty password",
            "pb.yml:6:19",
            "pb.yml:4:24",
        )
    ]


def test_matches_2_chain_variable_on_task(tmp_path: Path) -> None:
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
        results = stringify(EmptyPasswordRule().check(context))

    assert results == [
        _result(
            "`args.password` is set to an empty password",
            "pb.yml:7:19",
            "pb.yml:4:24",
        )
    ]


def test_matches_variable_name_with_literal(tmp_path: Path) -> None:
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
        results = stringify(EmptyPasswordRule().check(context))

    assert results == [
        _result(
            "`secret_password` is set to an empty password",
            "pb.yml:4:17",
            "pb.yml:4:34",
        )
    ]


def test_matches_indirect_variable_name(tmp_path: Path) -> None:
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
        results = stringify(EmptyPasswordRule().check(context))

    assert results == [
        _result(
            "`secret_password` is set to an empty password",
            "pb.yml:5:17",
            "pb.yml:4:24",
        )
    ]


@pytest.mark.xfail(reason="nested key in dict literal")
def test_glitch_empty_password(tmp_path: Path) -> None:
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
        make_result(
            EmptyPasswordRule.code,
            "`args.password` is set to an empty password",
            "pb.yml:4:19",
        )
    ]
