from __future__ import annotations

from typing import TYPE_CHECKING

from semantics_helpers import (  # pyright: ignore[reportImplicitRelativeImport]
    build_graph,
    run_all_checks,
    write_yaml,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_include_vars(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              tasks:
                - include_vars: vars.yml
                - debug:
                    msg: '{{ a }}'
        """,
        pb_path,
    )
    write_yaml("a: 123", tmp_path / "vars.yml")
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    assert results == [
        (
            "SEM003",
            "Unnecessary use of include_vars for variable `a@0`",
            "vars.yml:1:1\n\tvia pb.yml:4:19",
            None,
        )
    ]
