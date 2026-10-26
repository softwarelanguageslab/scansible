from __future__ import annotations

from typing import TYPE_CHECKING

from semantics_helpers import (  # pyright: ignore[reportImplicitRelativeImport]
    build_graph,
    run_all_checks,
    write_yaml,
)

if TYPE_CHECKING:
    from pathlib import Path


def test_impure_expression(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              vars:
                abc: 'test-{{ 9999 | random }}'
              tasks:
                - debug:
                    msg: '{{ abc }}'
                - debug:
                    msg: '{{ abc }} 2'
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    assert results == [
        (
            "SEM001",
            "Potentially unsafe reuse of variable `abc@0` due to an impure expression",
            "pb.yml:4:17",
            "pb.yml:4:22",
        )
    ]


def test_redefined_dependence(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              vars:
                abc: 123
                x: '{{ abc + 5 }}'
              tasks:
                - debug:
                    msg: '{{ x }}'
                - set_fact:
                    abc: '{{ 9999 | random }}'
                  when: abc == 123
                - debug:
                    msg: '{{ x }}'
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    assert results == [
        (
            "SEM001",
            "Potentially unsafe reuse of variable `x@0` due to a redefined dependency",
            "pb.yml:5:17",
            "pb.yml:10:21",
        )
    ]


def test_no_change(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              vars:
                abc: 123
                x: '{{ abc + 5 }}'
              tasks:
                - debug:
                    msg: '{{ x }}'
                - debug:
                    msg: '{{ x }} again'
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    # x is reused with no redefinition of its dependencies and nothing impure
    # involved, so the value-version bump alone must not be flagged.
    assert not results


def test_eager_impure_dependency_reused(tmp_path: Path) -> None:
    pb_path = tmp_path / "pb.yml"
    write_yaml(
        """
            - hosts: localhost
              vars:
                y: '{{ abc }}'
              tasks:
                - set_fact:
                    abc: '{{ 9999 | random }}'
                - debug:
                    msg: '{{ y }}'
                - debug:
                    msg: '{{ y }} again'
        """,
        pb_path,
    )
    ctx = build_graph(pb_path)

    results = run_all_checks(ctx)

    # abc is set_fact'ed (eager) so its value-version stays constant across
    # reuses even though it's impure; y's own reuse must not be flagged.
    assert not results
