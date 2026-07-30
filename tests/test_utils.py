# pyright: reportUnusedFunction = false

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from scansible.representations.ast import TaskFile
from scansible.utils import (
    ProjectPath,
    SourceFileMap,
    capture_output,
    find_all_files,
    find_file,
)


def describe_source_file_map() -> None:
    f1 = object()
    f2 = object()

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
        map = SourceFileMap[object]([("main.yml", f1), ("other.yaml", f2)])

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
        map = SourceFileMap[object]([("main.yml", f1), ("other.yaml", f2)])

        def should_contain_both_keys() -> None:
            assert "main" in map
            assert "other" in map

        def should_not_contain_other_key() -> None:
            assert "yet-another" not in map

        def should_return_files() -> None:
            assert map["main"] is f1
            assert map["other"] is f2

    def describe_file_map_with_conflicting_extensions() -> None:
        map = SourceFileMap[object]([("main.yml", f1), ("main.yaml", f2)])

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
        map = SourceFileMap[object]([("tasks/main.yml", f1), ("tasks/other.yaml", f2)])

        def should_contain_both_keys() -> None:
            assert "tasks/main" in map
            assert "tasks/other" in map

        def should_return_files() -> None:
            assert map["tasks/main"] is f1
            assert map["tasks/other"] is f2

    def describe_file_map_with_subdirectory_and_prefix() -> None:
        map = SourceFileMap[object](
            [("tasks/main.yml", f1), ("tasks/other.yaml", f2)], prefix="tasks/"
        )

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


def describe_project_path():
    def describe_ctor():
        @pytest.mark.parametrize(
            "child_path",
            ["meta/main.yml", Path("meta/main.yml"), Path("meta/main.yml").absolute()],
        )
        def should_support_various_types_of_child_paths(child_path: str | Path):
            pp = ProjectPath(Path().absolute(), child_path)

            assert pp.root == Path().absolute()
            assert pp.relative == Path("meta/main.yml")
            assert pp.absolute == Path("meta/main.yml").absolute()

        def should_reject_relative_root_paths():
            with pytest.raises(ValueError, match="absolute path"):
                _ = ProjectPath(Path("."), "test.yml")

    def describe_from_root():
        def should_construct_correct_path():
            pp = ProjectPath.from_root(Path().absolute())

            assert pp.root == Path().absolute()
            assert pp.absolute == Path().absolute()
            assert pp.relative == Path(".")

    def describe_join():
        @pytest.mark.parametrize(
            "child_path", ["main.yml", Path("main.yml"), Path("main.yml").absolute()]
        )
        def should_support_various_types_of_child_paths(child_path: str | Path):
            rpp = ProjectPath.from_root(Path().absolute())
            pp = rpp.join(child_path)

            assert pp.root == rpp.root
            assert pp.relative == Path("main.yml")
            assert pp.absolute == Path("main.yml").absolute()

        def should_remember_root_path():
            rpp = ProjectPath.from_root(Path().absolute())
            pp1 = rpp.join("meta")
            pp2 = pp1.join("main.yml")

            assert pp2.root == rpp.root
            assert pp2.relative == Path("meta/main.yml")

        # FIXME
        @pytest.mark.xfail(reason="not implemented any longer")
        def should_reject_child_with_different_parent():
            rpp = ProjectPath.from_root(Path("meta").absolute())
            with pytest.raises(Exception):  # noqa: B017 # FIXME
                _ = rpp.join(Path("tasks/main.yml").absolute())


def describe_find_file():
    @pytest.mark.parametrize("ext", ["yml", "yaml", "json"])
    def should_find_valid_files(tmp_path: Path, ext: str):
        (tmp_path / f"test.{ext}").touch()

        result = find_file(ProjectPath.from_root(tmp_path), "test")

        assert result and result.relative == Path(f"test.{ext}")

    def should_not_find_files_that_dont_exist(tmp_path: Path):
        result = find_file(ProjectPath.from_root(tmp_path), "test")

        assert result is None


def describe_find_all_files():
    def should_find_all_files(tmp_path: Path):
        (tmp_path / "test.yml").touch()
        (tmp_path / "main.yml").touch()
        rp = ProjectPath.from_root(tmp_path)

        result = find_all_files(rp)

        assert {child.absolute for child in result} == {
            rp.absolute / "test.yml",
            rp.absolute / "main.yml",
        }

    def should_find_files_in_nested_dirs(tmp_path: Path):
        (tmp_path / "test.yml").touch()
        (tmp_path / "tasks").mkdir()
        (tmp_path / "tasks" / "main.yml").touch()
        rp = ProjectPath.from_root(tmp_path)

        result = find_all_files(rp)

        assert {child.absolute for child in result} == {
            rp.absolute / "test.yml",
            rp.absolute / "tasks" / "main.yml",
        }

    def should_ignore_files_with_unknown_extensions(tmp_path: Path):
        (tmp_path / "test.txt").touch()
        rp = ProjectPath.from_root(tmp_path)

        result = find_all_files(rp)

        assert not result


def describe_capture_output():
    def should_capture_output_to_stdout():
        with capture_output() as out:
            print("hello world")

        assert out.getvalue() == "hello world\n"

    def should_capture_output_to_stderr():
        with capture_output() as out:
            print("hello world", file=sys.stderr)

        assert out.getvalue() == "hello world\n"

    def should_capture_output_to_stdout_and_stderr():
        with capture_output() as out:
            print("hello", file=sys.stderr)
            print("world")

        assert out.getvalue() == "hello\nworld\n"
