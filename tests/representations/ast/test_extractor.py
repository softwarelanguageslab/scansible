# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

from _constants import (  # pyright: ignore[reportImplicitRelativeImport]
    DEFAULTS,
    HANDLERS,
    META,
    ROLE_VARS,
    TASKS,
)

from scansible.representations.ast import (
    Play,
    Playbook,
    Role,
    extract_playbook,
    extract_role,
)


def describe_extracting_playbook():
    def extracts_correct_playbook(tmp_path: Path):
        pb_content = """
            ---
            - hosts: servers
              name: config servers
              tasks:
                - file:
                    path: test.txt
                    state: present
              vars:
                x: 111
        """
        _ = (tmp_path / "pb.yml").write_text(dedent(pb_content))

        result = extract_playbook(tmp_path / "pb.yml", lenient=False)

        assert result.is_playbook
        assert not result.is_role
        assert result.path == tmp_path / "pb.yml"
        assert isinstance(result.root, Playbook)
        assert result.root.path == Path("pb.yml")
        assert len(result.root.plays) == 1
        assert isinstance(result.root.plays[0], Play)
        assert not result.broken_files
        assert not result.broken_tasks

    def ignores_malformed_plays_in_lenient_mode(tmp_path: Path):
        pb_content = """
            ---
            - name: config servers
              tasks: []
        """
        _ = (tmp_path / "pb.yml").write_text(dedent(pb_content))

        result = extract_playbook(tmp_path / "pb.yml", lenient=True)

        assert isinstance(result.root, Playbook)
        assert len(result.root.plays) == 0
        assert len(result.broken_tasks) == 1


def describe_extracting_roles():
    def extracts_correct_roles(tmp_path: Path):
        for dirname in ("meta", "tasks", "vars", "defaults", "handlers"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "meta" / "main.yml").write_text(dedent(META))
        _ = (tmp_path / "tasks" / "main.yml").write_text(dedent(TASKS))
        _ = (tmp_path / "defaults" / "main.yml").write_text(dedent(DEFAULTS))
        _ = (tmp_path / "vars" / "main.yml").write_text(dedent(ROLE_VARS))
        _ = (tmp_path / "handlers" / "main.yml").write_text(dedent(HANDLERS))

        result = extract_role(tmp_path)

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, Role)
        assert result.path == tmp_path
        assert result.root.path == Path(".")
        assert not result.broken_files
        assert not result.broken_tasks
