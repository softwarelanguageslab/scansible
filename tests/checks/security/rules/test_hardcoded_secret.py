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

from scansible.checks.security.rules.hardcoded_secret import HardcodedSecretRule

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, HardcodedSecretRule.code)


def test_matches_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(HardcodedSecretRule().check(context))

    assert results == [
        _result(
            "`args.password` contains a hardcoded secret",
            "pb.yml:4:19",
            "pb.yml:7:31",
        )
    ]


def test_matches_variable_on_task(tmp_path: Path) -> None:
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
        results = stringify(HardcodedSecretRule().check(context))

    assert results == [
        _result(
            "`args.password` contains a hardcoded secret",
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
        results = stringify(HardcodedSecretRule().check(context))

    assert results == [
        _result(
            "`args.password` contains a hardcoded secret",
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
                secret_password: sekrit
              tasks:
                - debug: msg={{ secret_password }}
        """,
        pb_path,
    )
    with temp_import_pb(pb_path) as context:
        results = stringify(HardcodedSecretRule().check(context))

    assert results == [
        _result(
            "`secret_password` contains a hardcoded secret",
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
                a_var: sekrit
                secret_password: '{{ a_var }}'
              tasks:
                - debug: msg={{ secret_password }}
        """,
        pb_path,
    )
    with temp_import_pb(pb_path) as context:
        results = stringify(HardcodedSecretRule().check(context))

    assert results == [
        _result(
            "`secret_password` contains a hardcoded secret",
            "pb.yml:5:17",
            "pb.yml:4:24",
        )
    ]


def test_does_not_match_update_password_flag_as_literal(tmp_path: Path) -> None:
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
        results = stringify(HardcodedSecretRule().check(context))

    assert not results


def test_does_not_match_update_password_flag_as_expression(tmp_path: Path) -> None:
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
        results = stringify(HardcodedSecretRule().check(context))

    assert not results


def test_does_not_match_vault_value(tmp_path: Path) -> None:
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
        results = stringify(HardcodedSecretRule().check(context))

    assert not results


def test_does_not_match_variable_from_inventory(tmp_path: Path) -> None:
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
        results = stringify(HardcodedSecretRule().check(context))

    assert not results


def test_does_not_match_task_key_in_whitelist(tmp_path: Path) -> None:
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
        results = stringify(HardcodedSecretRule().check(context))

    assert not results


@pytest.mark.xfail(reason="nested key in dict literal")
def test_glitch_hardcoded_secret(tmp_path: Path) -> None:
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
        make_result(
            HardcodedSecretRule.code,
            "`args.password` contains a hardcoded secret",
            "pb.yml:4:19",
            "pb.yml:10:33",
        )
    ]
