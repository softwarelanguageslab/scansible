# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scansible.representations.ast import ExtractionContext, Handler, HandlerFile
from scansible.utils import ProjectPath


def describe_extracting_handler_files():
    def extracts_standard_handler_files(tmp_path: Path):
        yaml = """
            - name: restart service
              service:
                name: test
                state: restarted
            - name: restart other
              service:
                name: other
                state: restarted
              listen: a topic
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.handlers) == 2
        assert isinstance(result.handlers[0], Handler)
        assert isinstance(result.handlers[1], Handler)
        assert result.handlers[0].name == "restart service"
        assert result.handlers[1].listen == ["a topic"]

    def allows_handler_files_to_be_empty(tmp_path: Path):
        yaml = "# just a comment"
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(False)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert not result.handlers

    @pytest.mark.parametrize("content", ["hello: world"])  # dict  # string
    def rejects_invalid_files(tmp_path: Path, content: str):
        _ = (tmp_path / "main.yml").write_text(content)
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

    def ignores_malformed_handler_in_lenient_mode(tmp_path: Path):
        yaml = """
            - name: test
              file:
                path: test.txt
              apt:
                name: test.txt
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(True)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.handlers) == 0
        assert len(ctx.broken_tasks) == 1
