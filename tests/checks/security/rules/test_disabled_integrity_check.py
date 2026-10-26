from __future__ import annotations

from typing import TYPE_CHECKING

from functools import partial

from security_helpers import (  # pyright: ignore[reportImplicitRelativeImport]
    make_result,
    stringify,
    temp_import_pb,
    write_pb,
)

from scansible.checks.security.rules.disabled_integrity_check import (
    DisabledIntegrityCheckRule,
)

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, DisabledIntegrityCheckRule.code)


def test_matches_disabled_gpgcheck(tmp_path: Path) -> None:
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
        results = stringify(DisabledIntegrityCheckRule().check(context))

    assert results == [
        _result(
            "`args.gpgcheck` disables the integrity check",
            "pb.yml:4:19",
            "pb.yml:6:31",
        )
    ]


def test_matches_inverted_disabled_gpgcheck(tmp_path: Path) -> None:
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
        results = stringify(DisabledIntegrityCheckRule().check(context))

    assert results == [
        _result(
            "`args.disable_gpg_check` disables the integrity check",
            "pb.yml:4:19",
            "pb.yml:6:40",
        )
    ]


def test_matches_disabled_gpgcheck_indirectly(tmp_path: Path) -> None:
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
        results = stringify(DisabledIntegrityCheckRule().check(context))

    assert results == [
        _result(
            "`args.gpgcheck` disables the integrity check",
            "pb.yml:6:19",
            "pb.yml:4:25",
        )
    ]


def test_does_not_match_enabled_gpgcheck(tmp_path: Path) -> None:
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
        results = stringify(DisabledIntegrityCheckRule().check(context))

    assert not results


def test_does_not_match_inverted_enabled_gpgcheck(tmp_path: Path) -> None:
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
        results = stringify(DisabledIntegrityCheckRule().check(context))

    assert not results
