# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scansible.representations.ast import Block, ExtractionContext, Task, TaskFile
from scansible.utils import ProjectPath


def describe_extracting_tasks_file():
    def extracts_standard_task_files(tmp_path: Path):
        yaml = """
            - name: hello world
              file:
                path: hello
            - block:
                - name: test
                  test: {}
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = TaskFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.tasks) == 2
        assert isinstance(result.tasks[0], Task)
        assert isinstance(result.tasks[1], Block)

    def allows_task_files_to_be_empty(tmp_path: Path):
        yaml = "# just a comment"
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = TaskFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert not result.tasks

    @pytest.mark.parametrize("content", ["hello: world"])  # dict  # string
    def rejects_invalid_files(tmp_path: Path, content: str):
        _ = (tmp_path / "main.yml").write_text(content)
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = TaskFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

    def ignores_malformed_task_in_lenient_mode(tmp_path: Path):
        yaml = """
            - name: test
              file:
                path: test.txt
              apt:
                name: test.txt
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(True)

        result = TaskFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.tasks) == 0
        assert len(ctx.broken_tasks) == 1

    def ignores_malformed_block_in_lenient_mode(tmp_path: Path):
        yaml = """
            - rescue:
                - file: {}
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(True)

        result = TaskFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.tasks) == 0
        assert len(ctx.broken_tasks) == 1
