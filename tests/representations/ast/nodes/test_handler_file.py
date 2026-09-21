# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest

from scansible.ast import ExtractionContext, Handler, HandlerBlock, HandlerFile
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
        ctx = ExtractionContext(lenient=False)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.handlers) == 2
        h1, h2 = result.handlers
        assert isinstance(h1, Handler)
        assert isinstance(h2, Handler)
        assert h1.name == "restart service"
        assert h2.listen == ("a topic",)

    def allows_handler_files_to_be_empty(tmp_path: Path):
        yaml = "# just a comment"
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(lenient=False)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert not result.handlers

    def extracts_handler_files_with_blocks(tmp_path: Path):
        yaml = """
            - block:
                - name: restart service
                  service:
                    name: test
                    state: restarted
                  listen: block handler
                - name: restart other
                  service:
                    name: other
                    state: restarted
                  listen: block handler
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(lenient=False)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.handlers) == 1
        (b,) = result.handlers
        assert isinstance(b, HandlerBlock)
        assert len(b.block) == 2
        h1, _ = b.block
        assert isinstance(h1, Handler)
        assert h1.listen == ("block handler",)

    @pytest.mark.parametrize("content", ["hello: world"])  # dict  # string
    def rejects_invalid_files(tmp_path: Path, content: str):
        _ = (tmp_path / "main.yml").write_text(content)
        ctx = ExtractionContext(lenient=False)

        with pytest.raises(ValueError, match="Expected a sequence"):
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
        ctx = ExtractionContext(lenient=True)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.handlers) == 0
        assert len(ctx.broken_tasks) == 1

    def ignores_handler_block_with_malformed_nested_handler_in_lenient_mode(
        tmp_path: Path,
    ):
        yaml = """
            - block:
                - name: test
                  file:
                    path: test.txt
                  apt:
                    name: test.txt
        """
        _ = (tmp_path / "main.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(lenient=True)

        result = HandlerFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.handlers) == 0
        assert len(ctx.broken_tasks) == 1
