# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from scansible.representations.ast import ExtractionContext, VariableFile
from scansible.representations.ast.helpers import ProjectPath
from scansible.types import VaultValue


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
            "test3": ["hello", "world"],
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
        assert result.variables == {
            "postgres_passwd": VaultValue(
                data=b"$ANSIBLE_VAULT;1.1;AES256\n62396263313762316136336334303463366465303638626438616530343935623766626534366436\n",
                ansible_pos=(f"{tmp_path}/main.yml", 2, 22),
            ),
        }

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

    @pytest.mark.parametrize(
        "content",
        [
            "- hello\n- world",  # list instead of dict
            "test123",  # string instead of dict
            "1: 2\nabc: def",  # non-string keys.
        ],
    )
    def rejects_invalid_files(tmp_path: Path, content: str):
        _ = (tmp_path / "main.yml").write_text(content)
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

    @pytest.mark.parametrize(
        "identifier",
        ["123test", "un¡code™", "def", "for"],
    )
    def rejects_invalid_identifiers(tmp_path: Path, identifier: str):
        yaml = f"""
            {identifier}: 123
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = VariableFile.load(ProjectPath(tmp_path, "main.yml"), ctx)
