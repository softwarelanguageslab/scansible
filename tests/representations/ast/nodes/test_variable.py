# pyright: reportUnusedFunction = false

from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from scansible.representations.ast import ExtractionContext, VariableFile
from scansible.representations.ast.nodes.expression import (
    BoolLiteral,
    DateLiteral,
    DatetimeLiteral,
    FloatLiteral,
    IntLiteral,
    MapLiteral,
    SeqLiteral,
    StrLiteral,
)
from scansible.utils import ProjectPath


def describe_extracting_variables():
    def extracts_simple_variables(tmp_path: Path):
        yaml = """
            test: hello world
            test2: 123
            test3:
                - hello
                - world
            test4:
                this: is
                a: dict
        """
        ctx = ExtractionContext(False)
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))

        result = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert result.variables == {
            "test": "hello world",
            "test2": 123,
            "test3": ("hello", "world"),
            "test4": {"this": "is", "a": "dict"},
        }

    def extracts_vault_variables(tmp_path: Path):
        # ioannis1/pg_config/defaults/main.yml
        yaml = """
            postgres_passwd:     !vault |
                $ANSIBLE_VAULT;1.1;AES256
                62396263313762316136336334303463366465303638626438616530343935623766626534366436
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        (pwd,) = result.variables.values()
        assert isinstance(pwd, StrLiteral)
        assert (
            pwd
            == "$ANSIBLE_VAULT;1.1;AES256\n62396263313762316136336334303463366465303638626438616530343935623766626534366436\n"
        )
        assert pwd.is_vaulted
        assert pwd.__position__ == ("main.yml", (2, 22), (5, 1))

    def allows_variable_values_to_be_none(tmp_path: Path):
        yaml = """
            test:
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert result.variables == {"test": None}

    def allows_variable_files_to_be_empty(tmp_path: Path):
        yaml = """
            # just a comment
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert result.variables == {}

    def extracts_correct_types(tmp_path: Path):
        yaml = """
            a: hello
            b: 123
            c: 4.00
            d: yes
            e: 2026-01-01
            f: 2026-01-02T03:04:05Z
            g:
              - 123
              - abc
            h:
              x: 4.56
              y: true
            i: !unsafe "{{ unsafe }}"
            j: !vault |
                $ANSIBLE_VAULT;1.1;AES256
                62396263313762316136336334303463366465303638626438616530343935623766626534366436
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        a, b, c, d, e, f, g, h, i, j = result.variables.values()
        assert isinstance(a, StrLiteral)
        assert a == "hello"
        assert a.__position__ == ("main.yml", (2, 4), (2, 9))
        assert isinstance(b, IntLiteral)
        assert b == 123
        assert b.__position__ == ("main.yml", (3, 4), (3, 7))
        assert c == 4.0
        assert isinstance(c, FloatLiteral)
        assert c.__position__ == ("main.yml", (4, 4), (4, 8))
        assert isinstance(d, BoolLiteral)
        assert d == True  # noqa: E712
        assert d.__position__ == ("main.yml", (5, 4), (5, 7))
        assert isinstance(e, DateLiteral)
        assert e == date(2026, 1, 1)
        assert e.__position__ == ("main.yml", (6, 4), (6, 14))
        assert isinstance(f, DatetimeLiteral)
        assert f == datetime(2026, 1, 2, 3, 4, 5, tzinfo=f.tzinfo)
        assert f.__position__ == ("main.yml", (7, 4), (7, 24))
        assert isinstance(g, SeqLiteral)
        assert g == (123, "abc")
        assert isinstance(g[0], IntLiteral)
        assert isinstance(g[1], StrLiteral)
        assert g.__position__ == ("main.yml", (9, 3), (11, 1))
        assert isinstance(h, MapLiteral)
        assert h == {"x": 4.56, "y": True}
        assert h.__position__ == ("main.yml", (12, 3), (14, 1))
        assert isinstance(i, StrLiteral)
        assert i == "{{ unsafe }}"
        assert i.__position__ == ("main.yml", (14, 4), (14, 26))
        assert isinstance(j, StrLiteral)
        assert j.is_vaulted
        assert j.__position__ == ("main.yml", (15, 4), (18, 1))

    @pytest.mark.parametrize(
        "content",
        [
            "- hello\n- world",  # list instead of dict
            "test123",  # string instead of dict
        ],
    )
    def rejects_invalid_files(tmp_path: Path, content: str):
        _ = (tmp_path / "main.yml").write_text(content)
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)
