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

from scansible.checks.security.rules.admin_by_default import AdminByDefaultRule

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, AdminByDefaultRule.code)


def test_matches_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(AdminByDefaultRule().check(context))

    assert results == [
        _result(
            "`become_user` is set to an administrator account",
            "pb.yml:4:19",
            "pb.yml:5:32",
        )
    ]


def test_matches_variable_on_task(tmp_path: Path) -> None:
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
        results = stringify(AdminByDefaultRule().check(context))

    assert results == [
        _result(
            "`become_user` is set to an administrator account",
            "pb.yml:6:19",
            "pb.yml:4:28",
        )
    ]


def test_does_not_match_non_admin_user(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_pb(
        """
            - hosts: localhost
              tasks:
                - debug: msg=test
                  become_user: joe
        """,
        pb_path,
    )
    with temp_import_pb(pb_path) as context:
        results = stringify(AdminByDefaultRule().check(context))

    assert not results


def test_does_not_match_admin_in_non_user_keyword(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_pb(
        """
            - hosts: localhost
              tasks:
                - debug:
                    msg: admin
        """,
        pb_path,
    )
    with temp_import_pb(pb_path) as context:
        results = stringify(AdminByDefaultRule().check(context))

    assert not results


def test_glitch_admin_by_default(tmp_path: Path) -> None:
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
        make_result(
            AdminByDefaultRule.code,
            "`become_user` is set to an administrator account",
            "pb.yml:4:19",
            "pb.yml:5:32",
        )
    ]
