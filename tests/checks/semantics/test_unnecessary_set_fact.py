from __future__ import annotations

from typing import TYPE_CHECKING

from semantics_helpers import (  # pyright: ignore[reportImplicitRelativeImport]
    build_graph,
    run_all_checks,
    write_yaml,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_set_fact(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              tasks:
                - set_fact:
                    abc: 123
                - debug: msg={{abc}}
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    assert results == [
        (
            "SEM002",
            "Unnecessary use of set_fact for variable `abc@0`",
            "pb.yml:5:21",
            None,
        )
    ]


def test_set_fact_false_impure(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              tasks:
                - set_fact:
                    abc: '{{ 9999 | random }}'
                - debug: msg={{abc}}
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    assert not results


def test_set_fact_false_impure_conditional(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              tasks:
                - set_fact:
                    abc: 123
                  when: 9999 | random > 1000
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    assert not results
