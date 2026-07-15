# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path

import pytest

from scansible.representations.ast.common import Position, parse_file
from scansible.utils import ProjectPath


def describe_position():
    def defaults_to_synthetic():
        result = Position()

        assert result.is_synthetic is True
        assert result.start_line == -1

    def coerces_from_ansible_position_tuple():
        result = Position.model_validate(("file.yml", 3, 5))

        assert result.file == Path("file.yml")
        assert result.start_line == 3
        assert result.start_column == 5
        assert result.is_synthetic is False


def describe_parse_file():
    @pytest.mark.parametrize(
        "yaml_content,expected",
        [
            ("hello: world", {"hello": "world"}),
            ("- test\n- test2", ["test", "test2"]),
        ],
    )
    def should_parse_valid_yaml(tmp_path: Path, yaml_content: str, expected: object):
        _ = (tmp_path / "test.yml").write_text(yaml_content)

        result = parse_file(ProjectPath(tmp_path, "test.yml"))

        assert result == expected

    def should_raise_on_invalid_yaml(tmp_path: Path):
        _ = (tmp_path / "test.yml").write_text("hello:\n-world")

        with pytest.raises(Exception):
            _ = parse_file(ProjectPath(tmp_path, "test.yml"))
