# pyright: reportUnusedFunction = false

from __future__ import annotations

import sys
from pathlib import Path

import pytest

import scansible.representations.ast.helpers as h


def describe_project_path():
    def describe_ctor():
        @pytest.mark.parametrize(
            "child_path",
            ["meta/main.yml", Path("meta/main.yml"), Path("meta/main.yml").absolute()],
        )
        def should_support_various_types_of_child_paths(child_path: str | Path):
            pp = h.ProjectPath(Path().absolute(), child_path)

            assert pp.root == Path().absolute()
            assert pp.relative == Path("meta/main.yml")
            assert pp.absolute == Path("meta/main.yml").absolute()

        def should_reject_relative_root_paths():
            with pytest.raises(Exception):
                _ = h.ProjectPath(Path("."), "test.yml")

    def describe_from_root():
        def should_construct_correct_path():
            pp = h.ProjectPath.from_root(Path().absolute())

            assert pp.root == Path().absolute()
            assert pp.absolute == Path().absolute()
            assert pp.relative == Path(".")

    def describe_join():
        @pytest.mark.parametrize(
            "child_path", ["main.yml", Path("main.yml"), Path("main.yml").absolute()]
        )
        def should_support_various_types_of_child_paths(child_path: str | Path):
            rpp = h.ProjectPath.from_root(Path().absolute())
            pp = rpp.join(child_path)

            assert pp.root == rpp.root
            assert pp.relative == Path("main.yml")
            assert pp.absolute == Path("main.yml").absolute()

        def should_remember_root_path():
            rpp = h.ProjectPath.from_root(Path().absolute())
            pp1 = rpp.join("meta")
            pp2 = pp1.join("main.yml")

            assert pp2.root == rpp.root
            assert pp2.relative == Path("meta/main.yml")

        @pytest.mark.xfail(reason="not implemented any longer")
        def should_reject_child_with_different_parent():
            rpp = h.ProjectPath.from_root(Path("meta").absolute())
            with pytest.raises(Exception):
                _ = rpp.join(Path("tasks/main.yml").absolute())


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

        result = h.parse_file(h.ProjectPath(tmp_path, "test.yml"))

        assert result == expected

    def should_raise_on_invalid_yaml(tmp_path: Path):
        _ = (tmp_path / "test.yml").write_text("hello:\n-world")

        with pytest.raises(Exception):
            _ = h.parse_file(h.ProjectPath(tmp_path, "test.yml"))


def describe_find_file():
    @pytest.mark.parametrize("ext", ["yml", "yaml", "json"])
    def should_find_valid_files(tmp_path: Path, ext: str):
        (tmp_path / f"test.{ext}").touch()

        result = h.find_file(h.ProjectPath.from_root(tmp_path), "test")

        assert result and result.relative == Path(f"test.{ext}")

    def should_not_find_files_that_dont_exist(tmp_path: Path):
        result = h.find_file(h.ProjectPath.from_root(tmp_path), "test")

        assert result is None


def describe_find_all_files():
    def should_find_all_files(tmp_path: Path):
        (tmp_path / "test.yml").touch()
        (tmp_path / "main.yml").touch()
        rp = h.ProjectPath.from_root(tmp_path)

        result = h.find_all_files(rp)

        assert {child.absolute for child in result} == {
            rp.absolute / "test.yml",
            rp.absolute / "main.yml",
        }

    def should_find_files_in_nested_dirs(tmp_path: Path):
        (tmp_path / "test.yml").touch()
        (tmp_path / "tasks").mkdir()
        (tmp_path / "tasks" / "main.yml").touch()
        rp = h.ProjectPath.from_root(tmp_path)

        result = h.find_all_files(rp)

        assert {child.absolute for child in result} == {
            rp.absolute / "test.yml",
            rp.absolute / "tasks" / "main.yml",
        }

    def should_ignore_files_with_unknown_extensions(tmp_path: Path):
        (tmp_path / "test.txt").touch()
        rp = h.ProjectPath.from_root(tmp_path)

        result = h.find_all_files(rp)

        assert not result


def describe_capture_output():
    def should_capture_output_to_stdout():
        with h.capture_output() as out:
            print("hello world")

        assert out.getvalue() == "hello world\n"

    def should_capture_output_to_stderr():
        with h.capture_output() as out:
            print("hello world", file=sys.stderr)

        assert out.getvalue() == "hello world\n"

    def should_capture_output_to_stdout_and_stderr():
        with h.capture_output() as out:
            print("hello", file=sys.stderr)
            print("world")

        assert out.getvalue() == "hello\nworld\n"
