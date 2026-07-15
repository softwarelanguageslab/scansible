# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path

from scansible.representations.ast import Position


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
