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

from scansible.checks.security.rules.unrestricted_ip_address import (
    UnrestrictedIPAddressRule,
)

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, UnrestrictedIPAddressRule.code)


def test_matches_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(UnrestrictedIPAddressRule().check(context))

    assert results == [
        _result(
            "`args.bind` binds to an unrestricted IP address",
            "pb.yml:4:19",
            "pb.yml:5:27",
        )
    ]


def test_matches_indirect_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(UnrestrictedIPAddressRule().check(context))

    assert results == [
        _result(
            "`args.bind` binds to an unrestricted IP address",
            "pb.yml:6:19",
            "pb.yml:4:31",
        )
    ]


def test_does_not_match_10_0_0_0(tmp_path: Path) -> None:
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
        results = stringify(UnrestrictedIPAddressRule().check(context))

    assert not results


@pytest.mark.xfail(reason="unsupported literal type")
def test_glitch_unrestricted_ip_address(tmp_path: Path) -> None:
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
        make_result(
            UnrestrictedIPAddressRule.code,
            "`args.bind` binds to an unrestricted IP address",
            "pb.yml:4:19",
            "pb.yml:6:39",
        )
    ]
