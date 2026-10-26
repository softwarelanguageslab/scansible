from __future__ import annotations

from typing import TYPE_CHECKING

from semantics_helpers import (  # pyright: ignore[reportImplicitRelativeImport]
    build_graph,
    run_all_checks,
    write_yaml,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_unconditional(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              vars:
                abc: 123
              tasks:
                - debug: msg={{ abc }}
                - debug:
                    msg: '{{ abc }}'
                  vars:
                    abc: 456
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    assert results == [
        (
            "SEM004",
            "Variable `abc@1` unconditionally shadows a previous definition",
            "pb.yml:10:21",
            "pb.yml:4:17",
        )
    ]
