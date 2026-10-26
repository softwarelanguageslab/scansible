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

from scansible.checks.security.rules.weak_crypto import WeakCryptoAlgorithmRule

if TYPE_CHECKING:
    from pathlib import Path


_result = partial(make_result, WeakCryptoAlgorithmRule.code)


def test_matches_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(WeakCryptoAlgorithmRule().check(context))

    assert results == [
        _result(
            "`args.checksum` uses a weak cryptographic algorithm",
            "pb.yml:4:19",
            "pb.yml:6:31",
        )
    ]


def test_matches_indirect_literal_on_task(tmp_path: Path) -> None:
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
        results = stringify(WeakCryptoAlgorithmRule().check(context))

    assert results == [
        _result(
            "`args.checksum` uses a weak cryptographic algorithm",
            "pb.yml:6:19",
            "pb.yml:4:32",
        )
    ]


def test_matches_usage_in_expressions(tmp_path: Path) -> None:
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
        results = stringify(WeakCryptoAlgorithmRule().check(context))

    assert results == [
        _result(
            "`args.password` uses a weak cryptographic algorithm",
            "pb.yml:4:19",
            "pb.yml:6:31",
        )
    ]


def test_glitch_weak_crypto(tmp_path: Path) -> None:
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
            make_result(
                WeakCryptoAlgorithmRule.code,
                "`args._raw_params` uses a weak cryptographic algorithm",
                "pb.yml:8:19",
                "pb.yml:6:38",
            ),
            # Due to the whole shell command expression containing "md5" as a substring.
            make_result(
                WeakCryptoAlgorithmRule.code,
                "`args._raw_params` uses a weak cryptographic algorithm",
                "pb.yml:8:19",
                "pb.yml:9:26",
            ),
        ]
    )
