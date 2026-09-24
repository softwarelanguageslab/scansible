# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from _constants import (  # pyright: ignore[reportImplicitRelativeImport]
    BROKEN_TASKS,
    DEFAULTS,
    HANDLERS,
    META,
    ROLE_VARS,
    TASKS,
)

from scansible.ast import ExtractionContext, Role
from scansible.utils import ProjectPath


def describe_extracting_roles():
    def extracts_correct_roles(tmp_path: Path):
        for dirname in ("meta", "tasks", "vars", "defaults", "handlers"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "meta" / "main.yml").write_text(META)
        _ = (tmp_path / "tasks" / "main.yml").write_text(TASKS)
        _ = (tmp_path / "defaults" / "main.yml").write_text(DEFAULTS)
        _ = (tmp_path / "vars" / "main.yml").write_text(ROLE_VARS)
        _ = (tmp_path / "handlers" / "main.yml").write_text(HANDLERS)
        ctx = ExtractionContext(lenient=False)

        result = Role.load(ProjectPath.from_root(tmp_path), ctx)

        assert result.path == Path()
        tf = result.main_tasks_file
        assert tf is not None
        assert len(result.task_files) == 1
        assert tf == result.task_files["main"]
        assert tf.path == Path("tasks/main.yml")
        assert len(tf.tasks) == 2
        mf = result.meta_file
        assert mf is not None
        assert mf.path == Path("meta/main.yml")
        assert len(mf.metablock.platforms) == 1
        assert not mf.metablock.dependencies
        vf = result.main_vars_file
        assert vf is not None
        assert len(result.role_var_files) == 1
        assert vf == result.role_var_files["main"]
        assert vf.path == Path("vars/main.yml")
        assert vf.variables == {"b": 456}
        df = result.main_defaults_file
        assert df is not None
        assert len(result.default_var_files) == 1
        assert df == result.default_var_files["main"]
        assert df.path == Path("defaults/main.yml")
        assert df.variables == {"a": 123}
        hf = result.main_handlers_file
        assert hf is not None
        assert len(result.handler_files) == 1
        assert hf == result.handler_files["main"]
        assert hf.path == Path("handlers/main.yml")
        assert len(hf.handlers) == 1

    def extracts_roles_with_files_missing(tmp_path: Path):
        for dirname in ("tasks", "defaults"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "tasks" / "main.yml").write_text(TASKS)
        _ = (tmp_path / "defaults" / "main.yml").write_text(DEFAULTS)
        ctx = ExtractionContext(lenient=False)

        result = Role.load(ProjectPath.from_root(tmp_path), ctx)

        assert result.path == Path()
        assert len(result.task_files) == 1
        assert len(result.default_var_files) == 1
        assert len(result.role_var_files) == 0
        assert len(result.handler_files) == 0
        assert result.meta_file is None
        assert result.main_tasks_file is not None
        assert result.main_defaults_file is not None
        assert result.main_vars_file is None
        assert result.main_handlers_file is None

    def extracts_roles_with_broken_files(tmp_path: Path):
        for dirname in ("tasks", "defaults"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "tasks" / "main.yml").write_text(BROKEN_TASKS)
        _ = (tmp_path / "defaults" / "main.yml").write_text(DEFAULTS)
        ctx = ExtractionContext(lenient=False)

        result = Role.load(ProjectPath.from_root(tmp_path), ctx)

        assert result.path == Path()
        assert len(result.task_files) == 0
        assert len(result.default_var_files) == 1
        assert len(result.role_var_files) == 0
        assert len(result.handler_files) == 0
        assert result.meta_file is None
        assert result.main_tasks_file is None
        assert result.main_defaults_file is not None
        assert result.main_vars_file is None
        assert result.main_handlers_file is None
        assert len(ctx.broken_files) == 1
        assert ctx.broken_files[0].path == Path("tasks/main.yml")

    def extracts_roles_with_broken_meta_file(tmp_path: Path):
        broken_meta = """
            galaxy_info:
                - test
                - test2
        """
        for dirname in ("meta", "tasks", "defaults"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "meta" / "main.yml").write_text(dedent(broken_meta))
        _ = (tmp_path / "tasks" / "main.yml").write_text(TASKS)
        _ = (tmp_path / "defaults" / "main.yml").write_text(DEFAULTS)
        ctx = ExtractionContext(lenient=False)

        result = Role.load(ProjectPath.from_root(tmp_path), ctx)

        assert result.path == Path()
        assert result.meta_file is None
        assert len(result.task_files) == 1
        assert len(result.default_var_files) == 1
        assert len(ctx.broken_files) == 1
        assert ctx.broken_files[0].path == Path("meta/main.yml")

    def extracts_roles_with_non_main_files(tmp_path: Path):
        tasks_1 = """
            - file:
                path: hello
            - import_tasks: other.yml
        """
        tasks_2 = """
            - apt:
                name: test
        """
        for dirname in ("tasks", "defaults"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "tasks" / "main.yml").write_text(dedent(tasks_1))
        _ = (tmp_path / "tasks" / "other.yml").write_text(dedent(tasks_2))
        _ = (tmp_path / "defaults" / "main.yml").write_text(DEFAULTS)

        ctx = ExtractionContext(lenient=False)

        result = Role.load(ProjectPath.from_root(tmp_path), ctx, extract_all=True)

        assert result.path == Path()
        assert len(result.task_files) == 2
        assert len(result.default_var_files) == 1
        assert len(result.role_var_files) == 0
        assert len(result.handler_files) == 0
        assert result.meta_file is None
        assert result.main_tasks_file == result.task_files["main"]
        assert result.main_defaults_file is not None
        assert result.main_vars_file is None
        assert result.main_handlers_file is None
        assert "other" in result.task_files
        other = result.task_files["other"]
        assert other.path == Path("tasks/other.yml")
        assert len(other.tasks) == 1
