# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path

import pytest

from scansible.representations.structural.ast import SourceFileMap, TaskFile


def describe_source_file_map() -> None:

    def describe_empty_file_map() -> None:
        map = SourceFileMap[TaskFile]([])

        def should_be_empty() -> None:
            assert len(map) == 0

        def should_be_falsy() -> None:
            assert not map

        def should_not_contain_key() -> None:
            assert "test" not in map

        def should_raise_keyerror() -> None:
            with pytest.raises(KeyError):
                map["test"]

    def describe_populated_file_map() -> None:
        f1 = TaskFile(path=Path("main.yml"), tasks=[])
        f2 = TaskFile(path=Path("other.yml"), tasks=[])
        map = SourceFileMap[TaskFile]([f1, f2])

        def should_have_length() -> None:
            assert len(map) == 2

        def should_be_truthy() -> None:
            assert map

        def should_contain_both_keys() -> None:
            assert "main" in map
            assert "other" in map

        def should_not_contain_other_key() -> None:
            assert "yet-another" not in map

        def should_return_files() -> None:
            assert map["main"] is f1
            assert map["other"] is f2

    def describe_file_map_with_mixed_extensions() -> None:
        f1 = TaskFile(path=Path("main.yml"), tasks=[])
        f2 = TaskFile(path=Path("other.yaml"), tasks=[])
        map = SourceFileMap[TaskFile]([f1, f2])

        def should_contain_both_keys() -> None:
            assert "main" in map
            assert "other" in map

        def should_not_contain_other_key() -> None:
            assert "yet-another" not in map

        def should_return_files() -> None:
            assert map["main"] is f1
            assert map["other"] is f2

    def describe_file_map_with_conflicting_extensions() -> None:
        f1 = TaskFile(path=Path("main.yml"), tasks=[])
        f2 = TaskFile(path=Path("main.yaml"), tasks=[])
        map = SourceFileMap[TaskFile]([f1, f2])

        def should_have_length() -> None:
            assert len(map) == 2

        def should_be_truthy() -> None:
            assert map

        def should_contain_key() -> None:
            assert "main" in map

        def should_prefer_yml() -> None:
            assert map["main"] is f1

        def should_enable_indexing_with_extension() -> None:
            assert map["main.yml"] is f1
            assert map["main.yaml"] is f2

    def describe_file_map_with_subdirectory() -> None:
        f1 = TaskFile(path=Path("tasks/main.yml"), tasks=[])
        f2 = TaskFile(path=Path("tasks/other.yaml"), tasks=[])
        map = SourceFileMap[TaskFile]([f1, f2])

        def should_contain_both_keys() -> None:
            assert "tasks/main" in map
            assert "tasks/other" in map

        def should_return_files() -> None:
            assert map["tasks/main"] is f1
            assert map["tasks/other"] is f2

    def describe_file_map_with_subdirectory_and_prefix() -> None:
        f1 = TaskFile(path=Path("tasks/main.yml"), tasks=[])
        f2 = TaskFile(path=Path("tasks/other.yaml"), tasks=[])
        map = SourceFileMap[TaskFile]([f1, f2], prefix="tasks/")

        def should_contain_both_keys() -> None:
            assert "main" in map
            assert "other" in map

        def should_contain_prefixed_keys() -> None:
            assert "tasks/main" in map
            assert "tasks/other" in map

        def should_return_files() -> None:
            assert map["main"] is f1
            assert map["other"] is f2

        def should_return_prefixed_files() -> None:
            assert map["tasks/main"] is f1
            assert map["tasks/other"] is f2
