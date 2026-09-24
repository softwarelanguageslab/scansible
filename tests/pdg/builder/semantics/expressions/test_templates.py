# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import NamedTuple

import pytest
from jinja2.compiler import DependencyFinderVisitor

from scansible import ast
from scansible.pdg.builder.semantics.expressions.templates import TemplateExpressionAST


class Case(NamedTuple):
    expr: str
    variables: set[str] = set()  # noqa: RUF012
    filters: set[str] = set()  # noqa: RUF012
    tests: set[str] = set()  # noqa: RUF012
    impure_components: set[str] = set()  # noqa: RUF012


test_cases = [
    Case(expr="{{ test_var }}", variables={"test_var"}),
    Case(expr='{{ "hello world" }}'),
    Case(expr="{{ 1 in [1, 2, 3] }}"),
    Case(expr="{{ myVar | default(0) }}", variables={"myVar"}, filters={"default"}),
    Case(expr="{{ myVar | default(omit) }}", variables={"myVar"}, filters={"default"}),
    Case(
        expr="{{ myVar | expanduser | basename }}",
        variables={"myVar"},
        filters={"expanduser", "basename"},
    ),
    Case(
        expr='{{ my_version is version("1.0.0", ">") }}',
        variables={"my_version"},
        tests={"version"},
    ),
    Case(
        expr='{{ lookup("file", "/etc/motd") }}',
        impure_components={"lookup 'file'"},
    ),
    Case(
        expr="{{ lookup(target, motdfile) }}",
        variables={"target", "motdfile"},
        impure_components={"lookup of non-constant (Name)"},
    ),
    Case(
        expr="The time is {{ now() }}",
        impure_components={"function 'now'"},
    ),
    Case(expr='Inline {{ expressions }} work {{ "too" }}!', variables={"expressions"}),
]


def _do_parse(case: Case) -> TemplateExpressionAST:
    expr = ast.Expression.model_validate(case.expr)
    return TemplateExpressionAST(expr)


@pytest.mark.parametrize("case", test_cases)
def describe_template_parser() -> None:
    def should_parse_expressions(case: Case) -> None:
        ast = _do_parse(case)

        assert ast is not None
        assert ast.ast_root is not None

    def should_find_variables(case: Case) -> None:
        ast = _do_parse(case)

        assert ast is not None
        assert ast.referenced_variables == case.variables

    def should_find_impure_components(case: Case) -> None:
        ast = _do_parse(case)

        assert ast is not None
        assert ast.is_pure == (not case.impure_components)
        assert set(ast.impure_components) == case.impure_components


@pytest.mark.parametrize("case", test_cases)
def describe_dependency_finder_visitor() -> None:
    def should_find_filters(case: Case) -> None:
        ast = _do_parse(case)
        visitor = DependencyFinderVisitor()

        visitor.visit(ast.ast_root)

        assert visitor.filters == case.filters

    def should_find_tests(case: Case) -> None:
        ast = _do_parse(case)
        visitor = DependencyFinderVisitor()

        visitor.visit(ast.ast_root)

        assert visitor.tests == case.tests
