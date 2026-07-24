# pyright: reportUnusedFunction = false

from __future__ import annotations

from datetime import date, datetime

import pytest
from _utils import parse_yaml_dict  # pyright: ignore[reportImplicitRelativeImport]
from jinja2 import nodes as j2_nodes
from pydantic import TypeAdapter, ValidationError

from scansible.representations.ast import ExtractionContext, Task
from scansible.representations.ast.nodes.expression import (
    BoolLiteral,
    Condition,
    DateLiteral,
    DatetimeLiteral,
    Expression,
    FloatLiteral,
    Identifier,
    IntLiteral,
    LenientSeqLiteral,
    MapLiteral,
    PercentLiteral,
    SeqLiteral,
    StrLiteral,
)


def describe_expression():
    def describe_valid():
        def parses_a_simple_expression():
            result = Expression.model_validate("{{ myvar }}")

            assert result.raw == "{{ myvar }}"
            [output] = result.template.body
            assert isinstance(output, j2_nodes.Output)

        def parses_an_expression_with_a_filter():
            result = Expression.model_validate("{{ myvar | default('x') }}")

            assert result.raw == "{{ myvar | default('x') }}"
            [output] = result.template.body
            assert isinstance(output, j2_nodes.Output)
            [node] = output.nodes
            assert isinstance(node, j2_nodes.Filter)

        def accepts_a_comment_only_expression():
            # A pure comment produces no output nodes at all, so it's correctly
            # not mistaken for non-templated literal text.
            result = Expression.model_validate("{# just a comment #}")

            assert result.raw == "{# just a comment #}"
            assert result.template.body == []

        def accepts_a_comment_followed_by_literal_text():
            # After stripping the comment, the remaining literal text ("Literal")
            # does not match `raw` verbatim, so this is also correctly not
            # mistaken for non-templated literal text.
            result = Expression.model_validate("{# comment #}Literal")

            assert result.raw == "{# comment #}Literal"
            [output] = result.template.body
            assert isinstance(output, j2_nodes.Output)
            [node] = output.nodes
            assert isinstance(node, j2_nodes.TemplateData)
            assert node.data == "Literal"

        def derives_position_from_a_yaml_node():
            value = parse_yaml_dict("x: '{{ myvar }}'")["x"]

            result = Expression.model_validate(value)

            assert not result.position.is_synthetic
            assert result.position == ("test.yaml", (1, 4), (1, 17))

        def uses_a_synthetic_position_for_plain_strings():
            result = Expression.model_validate("{{ myvar }}")

            assert result.position.is_synthetic

    def describe_invalid():
        def rejects_non_string_input():
            with pytest.raises(ValidationError, match="expressions must be strings"):
                _ = Expression.model_validate(123)

        def rejects_unsafe_strings():
            unsafe = parse_yaml_dict("x: !unsafe '{{ myvar }}'")["x"]

            with pytest.raises(
                ValidationError, match="refusing to treat an unsafe string"
            ):
                _ = Expression.model_validate(unsafe)

        def rejects_strings_without_jinja_delimiters():
            with pytest.raises(ValidationError, match="must contain Jinja2 delimiters"):
                _ = Expression.model_validate("This is not an expression")

        def rejects_malformed_syntax():
            with pytest.raises(ValidationError, match="invalid expression"):
                _ = Expression.model_validate("{{ x +")


def describe_condition():
    def describe_valid():
        def parses_a_bare_comparison():
            result = Condition.model_validate("x == 1")

            assert result.raw == "x == 1"
            assert isinstance(result, Expression)

        def parses_a_bare_test():
            result = Condition.model_validate("x is defined")

            assert result.raw == "x is defined"

        def wraps_the_condition_when_parsing():
            # The parsed template is the wrapped `{% if %}` tag's test expression,
            # not a plain "raw string as literal text" template.
            result = Condition.model_validate("x == 1")

            assert isinstance(result.template.body[0], j2_nodes.Compare)

    def describe_invalid():
        def rejects_non_string_input():
            with pytest.raises(ValidationError, match="expressions must be strings"):
                _ = Condition.model_validate(123)

        def rejects_unsafe_strings():
            unsafe = parse_yaml_dict("x: !unsafe 'x == 1'")["x"]

            with pytest.raises(
                ValidationError, match="refusing to treat an unsafe string"
            ):
                _ = Condition.model_validate(unsafe)

        def rejects_brace_wrapped_conditions():
            with pytest.raises(
                ValidationError, match="must not contain any Jinja2 brace syntax"
            ):
                _ = Condition.model_validate("{{ x == 1 }}")

        def rejects_malformed_syntax():
            with pytest.raises(ValidationError, match="invalid condition"):
                _ = Condition.model_validate("x ==")


def describe_identifier():
    @pytest.mark.parametrize("value", ["myvar", "_private", "camelCase"])
    def accepts_valid_identifiers(value: str):
        result = TypeAdapter(Identifier).validate_python(value)

        assert result == value

    @pytest.mark.parametrize(
        "value",
        [
            pytest.param("un¡code™", id="non-ascii"),
            pytest.param("foo-bar", id="not-an-identifier"),
            pytest.param("class", id="reserved-keyword"),
        ],
    )
    def rejects_invalid_identifiers(value: str):
        with pytest.raises(ValidationError):
            _ = TypeAdapter(Identifier).validate_python(value)


def describe_literals():
    def describe_str_literal():
        def coerces_plain_strings():
            result = TypeAdapter(StrLiteral).validate_python("hello")

            assert result == "hello"
            assert not result.is_vaulted

        def decodes_bytes():
            result = TypeAdapter(StrLiteral).validate_python(b"hello")

            assert result == "hello"

        def stringifies_non_strings():
            result = TypeAdapter(StrLiteral).validate_python(123)

            assert result == "123"

        def marks_vault_values_as_vaulted():
            vault_value = parse_yaml_dict("x: !vault secret")["x"]

            result = TypeAdapter(StrLiteral).validate_python(vault_value)

            assert result == "secret"
            assert result.is_vaulted

    def describe_int_literal():
        def accepts_ints():
            assert TypeAdapter(IntLiteral).validate_python(42) == 42

        def coerces_numeric_strings():
            assert TypeAdapter(IntLiteral).validate_python("42") == 42

        def rejects_truncating_floats():
            with pytest.raises(ValidationError, match="would be truncated"):
                _ = TypeAdapter(IntLiteral).validate_python("1.5")

        def rejects_non_numeric_strings():
            with pytest.raises(ValidationError):
                _ = TypeAdapter(IntLiteral).validate_python("abc")

    def describe_float_literal():
        def coerces_ints():
            assert TypeAdapter(FloatLiteral).validate_python(3) == 3.0

        def rejects_uncoercible_values():
            with pytest.raises(ValidationError):
                _ = TypeAdapter(FloatLiteral).validate_python(None)

    def describe_percent_literal():
        def strips_the_percent_sign():
            assert TypeAdapter(PercentLiteral).validate_python("50%") == 50.0

        def coerces_plain_numbers():
            assert TypeAdapter(PercentLiteral).validate_python(50) == 50.0

    def describe_bool_literal():
        @pytest.mark.parametrize(
            ["value", "expected"],
            [
                pytest.param("yes", True, id="yes"),
                pytest.param("on", True, id="on"),
                pytest.param("1", True, id="1"),
                pytest.param(True, True, id="bool-true"),
                pytest.param("no", False, id="no"),
                pytest.param("off", False, id="off"),
                pytest.param("0", False, id="0"),
                pytest.param(False, False, id="bool-false"),
            ],
        )
        def coerces_truthy_and_falsy_values(value: object, expected: bool):
            result = TypeAdapter(BoolLiteral).validate_python(value)

            assert result == expected

        def is_not_a_bool_subclass():
            result = TypeAdapter(BoolLiteral).validate_python(True)

            assert not isinstance(result, bool)
            assert bool(result) is True
            assert str(result) == "True"
            assert hash(result) == hash(True)

        def rejects_uncoercible_values():
            with pytest.raises(ValidationError):
                _ = TypeAdapter(BoolLiteral).validate_python("maybe")

    def describe_date_literal():
        def accepts_dates():
            value = date(2026, 1, 1)

            assert TypeAdapter(DateLiteral).validate_python(value) == value

        def rejects_non_dates():
            with pytest.raises(ValidationError):
                _ = TypeAdapter(DateLiteral).validate_python("2026-01-01")

    def describe_datetime_literal():
        def accepts_datetimes():
            value = datetime(2026, 1, 1, 1, 2, 3)

            assert TypeAdapter(DatetimeLiteral).validate_python(value) == value

        def rejects_non_datetimes():
            with pytest.raises(ValidationError):
                _ = TypeAdapter(DatetimeLiteral).validate_python("2026-01-01T01:02:03")

    def describe_seq_literal():
        def coerces_none_to_an_empty_tuple():
            assert TypeAdapter(SeqLiteral[int]).validate_python(None) == ()

        def wraps_a_scalar_in_a_one_tuple():
            assert TypeAdapter(SeqLiteral[int]).validate_python(5) == (5,)

        def passes_through_a_real_sequence():
            assert TypeAdapter(SeqLiteral[int]).validate_python([1, 2, 3]) == (1, 2, 3)

    def describe_lenient_seq_literal():
        def coerces_none_to_an_empty_tuple():
            assert TypeAdapter(LenientSeqLiteral[int]).validate_python(None) == ()

        def rejects_a_bare_scalar():
            with pytest.raises(ValidationError):
                _ = TypeAdapter(LenientSeqLiteral[int]).validate_python(5)

        def passes_through_a_real_sequence():
            result = TypeAdapter(LenientSeqLiteral[int]).validate_python([1, 2, 3])

            assert result == (1, 2, 3)

        def raises_on_invalid_items_when_strict():
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = TypeAdapter(LenientSeqLiteral[int]).validate_python(
                    [1, "nope", 3],
                    context=ctx,  # pyright: ignore[reportArgumentType]
                )

        def drops_invalid_items_when_lenient():
            ctx = ExtractionContext(lenient=True)

            result = TypeAdapter(LenientSeqLiteral[int]).validate_python(
                [1, "nope", 3],
                context=ctx,  # pyright: ignore[reportArgumentType]
            )

            assert result == (1, 3)
            assert len(ctx.broken_tasks) == 1
            assert ctx.broken_tasks[0].raw == "nope"

        def validates_real_ast_node_items():
            yaml = """
                name: hello world
                file:
                    path: test.txt
            """
            valid_task = parse_yaml_dict(yaml)

            result = TypeAdapter(LenientSeqLiteral[Task]).validate_python(
                [valid_task]
            )

            assert len(result) == 1
            assert isinstance(result[0], Task)
            assert result[0].action == "file"

        def drops_invalid_ast_node_items_when_lenient():
            yaml = """
                name: hello world
                file:
                    path: test.txt
            """
            valid_task = parse_yaml_dict(yaml)
            ctx = ExtractionContext(lenient=True)

            result = TypeAdapter(LenientSeqLiteral[Task]).validate_python(
                [valid_task, "not a task"],
                context=ctx,  # pyright: ignore[reportArgumentType]
            )

            assert len(result) == 1
            assert isinstance(result[0], Task)
            assert len(ctx.broken_tasks) == 1
            assert ctx.broken_tasks[0].raw == "not a task"

    def describe_map_literal():
        def coerces_none_to_an_empty_dict():
            assert TypeAdapter(MapLiteral[str, int]).validate_python(None) == {}

        def rejects_non_mappings():
            with pytest.raises(ValidationError):
                _ = TypeAdapter(MapLiteral[str, int]).validate_python([1, 2])

        def passes_through_a_real_mapping():
            result = TypeAdapter(MapLiteral[str, int]).validate_python({"a": 1})

            assert result == {"a": 1}

    def describe_position_tracking():
        def tracks_positions_for_scalar_literals():
            yaml = """
                a: hello
                b: 123
                c: 4.00
                d: yes
                e: 2026-01-01
                f: 2026-01-02T03:04:05Z
            """
            values = parse_yaml_dict(yaml)

            a = TypeAdapter(StrLiteral).validate_python(values["a"])
            assert a == "hello"
            assert a.__position__ == ("test.yaml", (2, 4), (2, 9))

            b = TypeAdapter(IntLiteral).validate_python(values["b"])
            assert b == 123
            assert b.__position__ == ("test.yaml", (3, 4), (3, 7))

            c = TypeAdapter(FloatLiteral).validate_python(values["c"])
            assert c == 4.0
            assert c.__position__ == ("test.yaml", (4, 4), (4, 8))

            d = TypeAdapter(BoolLiteral).validate_python(values["d"])
            assert d == True  # noqa: E712
            assert d.__position__ == ("test.yaml", (5, 4), (5, 7))

            e = TypeAdapter(DateLiteral).validate_python(values["e"])
            assert e == date(2026, 1, 1)
            assert e.__position__ == ("test.yaml", (6, 4), (6, 14))

            f = TypeAdapter(DatetimeLiteral).validate_python(values["f"])
            assert f == datetime(2026, 1, 2, 3, 4, 5, tzinfo=f.tzinfo)
            assert f.__position__ == ("test.yaml", (7, 4), (7, 24))

        def tracks_positions_for_composite_literals():
            yaml = """
                g:
                    - 123
                    - 456
                h:
                    x: 1
                    y: 2
            """
            values = parse_yaml_dict(yaml)

            g = TypeAdapter(SeqLiteral[IntLiteral]).validate_python(values["g"])
            assert g == (123, 456)
            assert g.__position__ == ("test.yaml", (3, 5), (5, 1))

            h = TypeAdapter(MapLiteral[StrLiteral, IntLiteral]).validate_python(
                values["h"]
            )
            assert h == {"x": 1, "y": 2}
            assert h.__position__ == ("test.yaml", (6, 5), (8, 1))
