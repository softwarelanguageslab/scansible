# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path

import pytest

from scansible.checks import CheckResult
from scansible.checks.semantics import run_all_checks as orig_run_all_checks
from scansible.representations.pdg import build_pdg
from scansible.representations.pdg.builder.context import BuildContext
from scansible.representations.pdg.representation import NodeLocation


def run_all_checks(ctx: BuildContext) -> list[CheckResult]:
    orig_results = orig_run_all_checks(ctx.graph, ctx.visibility_information)
    return [
        CheckResult(f"{res.rule_category}: {res.rule_name}", res.location)
        for res in orig_results
    ]


def build_graph(path: Path) -> BuildContext:
    return build_pdg(path, [])


def write_yaml(content: str, path: Path) -> None:
    _ = path.write_text(content)


def describe_unsafe_reuse_rules() -> None:
    def impure_expression(tmp_path: Path) -> None:
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
            CheckResult(
                "Unsafe reuse: Impure expression",
                NodeLocation(file="pb.yml", line=4, column=17),
            )
        ]

    @pytest.mark.xfail(
        reason="check is broken, as all expressions now get evaluated all the time"
    )
    def redefined_dependence(tmp_path: Path) -> None:
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
            CheckResult(
                "Unsafe reuse: Redefined dependence",
                NodeLocation(file="pb.yml", line=5, column=17),
            )
        ]


@pytest.mark.xfail(
    reason="check is broken, as unused variables are no longer added to the graph"
)
def describe_unintended_override_rules() -> None:
    def unconditional(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_yaml(
            """
            - hosts: localhost
              vars:
                abc: 123
              tasks:
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
            CheckResult(
                "Unintended override: Unconditional override",
                NodeLocation(file="pb.yml", line=9, column=21),
            )
        ]

    def unusable(tmp_path: Path) -> None:
        pb_path = tmp_path / "pb.yml"
        write_yaml(
            """
            - hosts: localhost
              tasks:
                - set_fact:
                    abc: '{{ 9999 | random }}'
                - debug:
                    msg: '{{ abc }}'
                  vars:
                    abc: 123
        """,
            pb_path,
        )
        ctx = build_graph(pb_path)

        results = run_all_checks(ctx)

        assert results == [
            CheckResult(
                "Unintended override: Unused because shadowed",
                NodeLocation(file="pb.yml", line=9, column=21),
            )
        ]


def describe_too_high_precedence_rules() -> None:
    def set_fact(tmp_path: Path) -> None:
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
            CheckResult(
                "Unnecessarily high precedence: Unnecessary set_fact",
                NodeLocation(file="pb.yml", line=5, column=21),
            )
        ]

    def set_fact_false_impure(tmp_path: Path) -> None:
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

    def set_fact_false_impure_conditional(tmp_path: Path) -> None:
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

    def include_vars(tmp_path: Path) -> None:
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
            CheckResult(
                "Unnecessarily high precedence: Unnecessary include_vars",
                NodeLocation(
                    file="vars.yml",
                    line=1,
                    column=1,
                    includer_location=NodeLocation(file="pb.yml", line=4, column=19),
                ),
            )
        ]
