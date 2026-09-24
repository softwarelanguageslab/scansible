# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import TYPE_CHECKING

from scansible.checks.base import CheckContext, Finding
from scansible.checks.semantics import get_all_rules
from scansible.pdg import build_pdg

if TYPE_CHECKING:
    from pathlib import Path

    from scansible.pdg.builder.context import BuildContext

#: A `Finding`, but with each `NodeLocation` collapsed down to its
#: `path:line:column` string to avoid deep positioning checks in tests.
type StringifiedResult = tuple[str, str, str, str | None]


def _stringify(results: list[Finding]) -> list[StringifiedResult]:
    return [
        (
            f.code,
            f.summary,
            str(f.location),
            str(f.hint_location) if f.hint_location is not None else None,
        )
        for f in results
    ]


def run_all_checks(ctx: BuildContext) -> list[StringifiedResult]:
    context = CheckContext(graph=ctx.graph)
    results = [finding for rule in get_all_rules() for finding in rule.check(context)]
    return _stringify(results)


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
            (
                "SEM001",
                "Potentially unsafe reuse of variable `abc@0` due to an impure expression",
                "pb.yml:4:17",
                "pb.yml:4:22",
            )
        ]

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
            (
                "SEM001",
                "Potentially unsafe reuse of variable `x@0` due to a redefined dependency",
                "pb.yml:5:17",
                "pb.yml:10:21",
            )
        ]

    def no_change(tmp_path: Path) -> None:
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

    def eager_impure_dependency_reused(tmp_path: Path) -> None:
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


def describe_variable_shadowing_rule() -> None:
    def unconditional(tmp_path: Path) -> None:
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
            (
                "SEM002",
                "Unnecessary use of set_fact for variable `abc@0`",
                "pb.yml:5:21",
                None,
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
            (
                "SEM003",
                "Unnecessary use of include_vars for variable `a@0`",
                "vars.yml:1:1\n\tvia pb.yml:4:19",
                None,
            )
        ]
