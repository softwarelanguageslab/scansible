# pyright: reportUnusedFunction = false, reportAny = false, reportExplicitAny = false

from __future__ import annotations

from typing import Any, cast

import io
import math
from pathlib import Path

import pytest
from ruamel.yaml import YAMLError

from scansible.cst import (
    YamlBool,
    YamlDate,
    YamlDatetime,
    YamlFloat,
    YamlInt,
    YamlMap,
    YamlNone,
    YamlSeq,
    YamlStr,
    YamlUnsafeStr,
    YamlVaultValue,
    parse_file,
)
from scansible.cst.constructor import CustomYAML
from scansible.utils import ProjectPath


def load(text: str, file_name: str = "test.yml") -> Any:
    """Helper to parse a YAML string directly.

    Returning Any to avoid type checking warnings in the tests.
    """
    return CustomYAML(file_name).load(io.StringIO(text))  # pyright: ignore[reportUnknownMemberType]


def describe_scalars():
    def describe_strings():
        @pytest.mark.parametrize(
            "yaml_value",
            [
                pytest.param("hello", id="plain"),
                pytest.param("'hello'", id="single-quoted"),
                pytest.param('"hello"', id="double-quoted"),
            ],
        )
        def resolves_to_yaml_str(yaml_value: str):
            result = load(f"key: {yaml_value}")["key"]

            assert isinstance(result, YamlStr)
            assert result == "hello"
            assert result.__position__.path == "test.yml"

        def preserves_multiline_position_for_block_literals():
            result = load("key: |\n  line1\n  line2\n")["key"]

            assert isinstance(result, YamlStr)
            assert result == "line1\nline2\n"
            assert result.__position__.start == (1, 6)
            assert result.__position__.end == (4, 1)

    def describe_ints():
        @pytest.mark.parametrize(
            ("yaml_value", "expected"),
            [
                pytest.param("42", 42, id="decimal"),
                pytest.param("-7", -7, id="negative"),
                pytest.param("0x1A", 26, id="hex"),
                pytest.param("017", 15, id="octal, YAML 1.1 syntax"),
                pytest.param("1_000", 1000, id="underscored"),
                pytest.param("1:20:30", 4830, id="sexagesimal, YAML 1.1 only"),
            ],
        )
        def resolves_to_yaml_int(yaml_value: str, expected: int):
            result = load(f"key: {yaml_value}")["key"]

            assert isinstance(result, YamlInt)
            assert result == expected
            assert result.__position__.path == "test.yml"

        def does_not_resolve_yaml_1_2_octal_syntax():
            # 0o17 is YAML 1.2 octal syntax; Ansible parses YAML 1.1, whose octal
            # syntax is a bare 0-prefix (017, tested above), so 0o17 stays a string.
            result = load("key: 0o17")["key"]

            assert isinstance(result, YamlStr)
            assert result == "0o17"

    def describe_floats():
        @pytest.mark.parametrize(
            ("yaml_value", "expected"),
            [
                pytest.param("1.5", 1.5, id="decimal"),
                pytest.param("1.5e+10", 1.5e10, id="scientific, signed exponent"),
                pytest.param(".inf", float("inf"), id="infinity"),
            ],
        )
        def resolves_to_yaml_float(yaml_value: str, expected: float):
            result = load(f"key: {yaml_value}")["key"]

            assert isinstance(result, YamlFloat)
            assert result == expected
            assert result.__position__.path == "test.yml"

        def resolves_nan():
            result = load("key: .nan")["key"]

            assert isinstance(result, YamlFloat)
            assert math.isnan(result)
            assert result.__position__.path == "test.yml"

        @pytest.mark.parametrize(
            "yaml_value",
            [
                pytest.param("1.5e10", id="scientific, unsigned exponent"),
                pytest.param("1e+10", id="scientific, no decimal point"),
            ],
        )
        def does_not_resolve_forms_ansible_rejects(yaml_value: str):
            # Ansible's YAML parser (PyYAML's Resolver) requires a decimal
            # point *and* a signed exponent for scientific notation, unlike
            # ruamel's more lenient defaults, so both stay plain strings.
            result = load(f"key: {yaml_value}")["key"]

            assert isinstance(result, YamlStr)
            assert result == yaml_value

    def describe_bools():
        @pytest.mark.parametrize(
            ("yaml_value", "expected"),
            [
                pytest.param("true", True, id="true"),
                pytest.param("false", False, id="false"),
                pytest.param("True", True, id="True"),
                pytest.param("yes", True, id="yes"),
                pytest.param("no", False, id="no"),
                pytest.param("on", True, id="on"),
                pytest.param("off", False, id="off"),
            ],
        )
        def resolves_to_yaml_bool(yaml_value: str, expected: bool):
            result = load(f"key: {yaml_value}")["key"]

            assert isinstance(result, YamlBool)
            assert not isinstance(result, bool)
            assert bool(result) is expected
            assert result == expected
            assert hash(result) == hash(expected)
            assert result.__position__.path == "test.yml"

        @pytest.mark.parametrize("yaml_value", ["y", "n", "Y", "N"])
        def does_not_resolve_bare_y_or_n(yaml_value: str):
            # Unlike the full YAML 1.1 spec, Ansible's parser (PyYAML's
            # Resolver) does not treat bare y/n as booleans, only the full
            # yes/no/on/off/true/false words, so these stay plain strings.
            result = load(f"key: {yaml_value}")["key"]

            assert isinstance(result, YamlStr)
            assert result == yaml_value

    def describe_nulls():
        @pytest.mark.parametrize(
            "yaml_value",
            [
                pytest.param("~", id="tilde"),
                pytest.param("null", id="null keyword"),
                pytest.param("", id="empty"),
            ],
        )
        def resolves_to_yaml_none(yaml_value: str):
            result = load(f"key: {yaml_value}")["key"]

            assert isinstance(result, YamlNone)
            assert result is not None
            assert result.__eq__(None) is True
            assert bool(result) is False
            assert hash(result) == hash(None)
            assert result.__position__.path == "test.yml"

    def describe_dates():
        def resolves_date_only_to_yaml_date():
            result = load("key: 2020-01-02")["key"]

            assert isinstance(result, YamlDate)
            assert not isinstance(result, YamlDatetime)
            assert result.isoformat() == "2020-01-02"
            assert result.__position__.start == (1, 6)
            assert result.__position__.end == (1, 16)

        def resolves_full_timestamp_to_yaml_datetime():
            result = load("key: 2020-01-02T03:04:05Z")["key"]

            assert isinstance(result, YamlDatetime)
            assert result.hour == 3
            assert result.minute == 4
            assert result.second == 5
            assert result.__position__.start == (1, 6)
            assert result.__position__.end == (1, 26)


def describe_vault_and_unsafe():
    def resolves_vault_value_with_multiline_position():
        result = load("key: !vault |\n  $ANSIBLE_VAULT;1.1;AES256\n  613233343536\n")[
            "key"
        ]

        assert isinstance(result, YamlVaultValue)
        assert result == "$ANSIBLE_VAULT;1.1;AES256\n613233343536\n"
        assert result.__position__.start == (1, 6)
        assert result.__position__.end == (4, 1)

    def resolves_vault_encrypted_tag_the_same_way():
        result = load("key: !vault-encrypted plaintext")["key"]

        assert isinstance(result, YamlVaultValue)
        assert result == "plaintext"

    def resolves_unsafe_string():
        result = load('key: !unsafe "some value"')["key"]

        assert isinstance(result, YamlUnsafeStr)
        assert result == "some value"
        assert result.__position__.start == (1, 6)
        assert result.__position__.end == (1, 26)


def describe_collections():
    def resolves_empty_map_and_seq():
        result = load("a: {}\nb: []\n")

        assert isinstance(result["a"], YamlMap)
        assert result["a"] == {}
        assert result["a"].__position__.start == (1, 4)
        assert result["a"].__position__.end == (1, 6)

        assert isinstance(result["b"], YamlSeq)
        assert result["b"] == []
        assert result["b"].__position__.start == (2, 4)
        assert result["b"].__position__.end == (2, 6)

    def resolves_flow_style_map_and_seq():
        result = load("a: {x: 1, y: 2}\nb: [1, 2, 3]\n")

        assert isinstance(result["a"], YamlMap)
        assert result["a"] == {"x": 1, "y": 2}
        assert result["a"].__position__.start == (1, 4)
        assert result["a"].__position__.end == (1, 16)

        assert isinstance(result["b"], YamlSeq)
        assert result["b"] == [1, 2, 3]
        assert result["b"].__position__.start == (2, 4)
        assert result["b"].__position__.end == (2, 13)

    def resolves_map_keys_of_non_string_scalar_types():
        result = load("1: a\n2: b\n")

        keys = list(result.keys())
        assert keys == [1, 2]
        assert all(isinstance(key, YamlInt) for key in keys)
        assert keys[0].__position__.start == (1, 1)
        assert keys[1].__position__.start == (2, 1)

    def resolves_nested_block_structures_with_position_per_node():
        result = load(
            "top:\n  - name: one\n    value: 1\n  - name: two\n    value: 2\n"
        )

        top = result["top"]
        assert isinstance(top, YamlSeq)
        assert top.__position__.start == (2, 3)
        assert top.__position__.end == (6, 1)

        item0: Any = cast(Any, top[0])
        assert isinstance(item0, YamlMap)
        assert item0.__position__.start == (2, 5)
        assert item0.__position__.end == (4, 3)
        assert cast(Any, item0["name"]).__position__.start == (2, 11)
        assert cast(Any, item0["value"]).__position__.start == (3, 12)

    def shares_position_between_anchor_and_alias():
        # Documenting existing/intended ruamel behavior: an aliased node
        # resolves to the *same object* as its anchor definition, so it also
        # shares its position rather than pointing at the alias reference.
        result = load("a: &anchor 5\nb: *anchor\n")

        assert result["a"] is result["b"]
        assert result["b"].__position__.start == (1, 4)
        assert result["b"].__position__.end == (1, 13)


def describe_parse_file():
    def wraps_top_level_value_with_relative_path(tmp_path: Path):
        _ = (tmp_path / "test.yml").write_text("key: value\n")

        result: Any = parse_file(ProjectPath(tmp_path, "test.yml"))

        assert result == {"key": "value"}
        assert isinstance(result, YamlMap)
        assert result.__position__.path == "test.yml"
        assert cast(Any, result["key"]).__position__.path == "test.yml"

    def uses_relative_path_for_nested_files(tmp_path: Path):
        (tmp_path / "sub").mkdir()
        _ = (tmp_path / "sub" / "nested.yml").write_text("key: value\n")

        result = parse_file(ProjectPath(tmp_path, "sub/nested.yml"))

        assert isinstance(result, YamlMap)
        assert result.__position__.path == str(Path("sub") / "nested.yml")

    def raises_on_invalid_yaml(tmp_path: Path):
        _ = (tmp_path / "bad.yml").write_text("hello:\n-world")

        with pytest.raises(YAMLError):
            _ = parse_file(ProjectPath(tmp_path, "bad.yml"))
