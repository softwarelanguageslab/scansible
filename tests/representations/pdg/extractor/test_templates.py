# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import NamedTuple

import pytest

from scansible.representations.pdg.extractor.expressions.templates import (
    LookupTarget,
    LookupTargetLiteral,
    LookupTargetVariable,
    TemplateExpressionAST,
)


class Case(NamedTuple):
    expr: str
    variables: set[str] = set()
    filters: set[str] = set()
    tests: set[str] = set()
    lookup_targets: set[LookupTarget] = set()
    uses_now: bool = False
    is_conditional: bool = False
    variable_mappings: dict[str, str] = {}


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
        lookup_targets={LookupTargetLiteral(name="file")},
    ),
    Case(
        expr="{{ lookup(target, motdfile) }}",
        variables={"target", "motdfile"},
        lookup_targets={LookupTargetVariable(name="target")},
    ),
    Case(expr="The time is {{ now() }}", uses_now=True),
    Case(expr='Inline {{ expressions }} work {{ "too" }}!', variables={"expressions"}),
]

conditional_test_cases = [
    Case(
        expr='url is match("http://example.com/users/.*/resources/")',
        variables={"url"},
        tests={"match"},
        is_conditional=True,
    ),
    Case(expr="my_items", variables={"my_items"}, is_conditional=True),
    Case(
        expr="my_items.keys() | list",
        variables={"my_items"},
        filters={"list"},
        is_conditional=True,
    ),
    Case(expr="{{ my_condition }}", variables={"my_condition"}, is_conditional=True),
    Case(
        expr="{{ my_condition }}",
        variables={"my_condition", "url"},
        tests={"match"},
        is_conditional=True,
        variable_mappings={"my_condition": 'url is match("*://example.*")'},
    ),
    Case(
        expr="item.last_updated < now()",
        variables={"item"},
        uses_now=True,
        is_conditional=True,
    ),
]


def _do_parse(case: Case) -> TemplateExpressionAST | None:
    if case.is_conditional:
        return TemplateExpressionAST.parse_conditional(
            case.expr, case.variable_mappings
        )
    return TemplateExpressionAST.parse(case.expr)


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

    def should_find_filters(case: Case) -> None:
        ast = _do_parse(case)

        assert ast is not None
        assert ast.used_filters == case.filters

    def should_find_tests(case: Case) -> None:
        ast = _do_parse(case)

        assert ast is not None
        assert ast.used_tests == case.tests

    def should_find_now_usage(case: Case) -> None:
        ast = _do_parse(case)

        assert ast is not None
        assert ast.uses_now == case.uses_now

    def should_find_lookups(case: Case) -> None:
        ast = _do_parse(case)

        assert ast is not None
        assert ast.used_lookups == case.lookup_targets
