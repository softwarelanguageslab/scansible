# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from _utils import parse_yaml_dict  # pyright: ignore[reportImplicitRelativeImport]

from scansible.representations.structural import (
    Block,
    ExtractionContext,
    Play,
    Playbook,
    Task,
)
from scansible.representations.structural.helpers import ProjectPath
from scansible.representations.structural.nodes.playbook import PlayRoleRequirement


def describe_extracting_plays():
    def extracts_simple_play():
        yaml = """
            name: test play
            hosts: servers
            tasks:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.tasks) == 1
        assert isinstance(result.tasks[0], Task)

    def extracts_play_with_block():
        yaml = """
            name: test play
            hosts: servers
            tasks:
              - block:
                - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.tasks) == 1
        assert isinstance(result.tasks[0], Block)

    def extracts_play_with_vars():
        yaml = """
            name: test play
            hosts: servers
            tasks:
              - import_tasks: test
            vars:
              testvar: 123
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.tasks) == 1
        assert isinstance(result.tasks[0], Task)
        assert result.vars == {"testvar": 123}

    def extracts_play_with_roles():
        yaml = """
            name: test play
            hosts: servers
            roles:
              - testrole
            tasks:
              - import_tasks: test
            vars:
              testvar: 123
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.roles) == 1
        assert isinstance(result.roles[0], PlayRoleRequirement)
        assert result.roles[0].role == "testrole"
        assert result.vars == {"testvar": 123}

    def rejects_invalid_play():
        # missing hosts
        yaml = """
            name: test play
            tasks:
                - import_tasks: hello
        """
        ctx = ExtractionContext(False)

        with pytest.raises(Exception):
            _ = Play.model_validate(parse_yaml_dict(yaml), context=ctx)


def describe_extracting_playbook():
    def extracts_correct_playbook(tmp_path: Path):
        yaml = """
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
        _ = (tmp_path / "pb.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(lenient=False)

        result = Playbook.load(ProjectPath(tmp_path, "pb.yml"), ctx)

        assert result.path == Path("pb.yml")
        assert len(result.plays) == 1
        assert isinstance(result.plays[0], Play)

    def extracts_playbooks_with_multiple_plays(tmp_path: Path):
        yaml = """
            ---
            - hosts: servers
              name: config servers
              tasks:
                - file:
                    path: test.txt
                    state: present
              vars:
                x: 111
            - hosts: databases
              name: config databases
              tasks: []
        """
        _ = (tmp_path / "pb.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(lenient=False)

        result = Playbook.load(ProjectPath(tmp_path, "pb.yml"), ctx)

        assert result.path == Path("pb.yml")
        assert len(result.plays) == 2
        assert isinstance(result.plays[0], Play)
        assert isinstance(result.plays[1], Play)

    def rejects_empty_playbooks(tmp_path: Path):
        _ = (tmp_path / "pb.yml").write_text("")
        ctx = ExtractionContext(lenient=False)

        with pytest.raises(Exception):
            _ = Playbook.load(ProjectPath(tmp_path, "pb.yml"), ctx)

    def ignores_malformed_plays_in_lenient_mode(tmp_path: Path):
        yaml = """
            ---
            - name: config servers
              tasks: []
        """
        _ = (tmp_path / "pb.yml").write_text(dedent(yaml))
        ctx = ExtractionContext(lenient=True)

        result = Playbook.load(ProjectPath(tmp_path, "pb.yml"), ctx)

        assert len(result.plays) == 0
        assert len(ctx.broken_tasks) == 1
