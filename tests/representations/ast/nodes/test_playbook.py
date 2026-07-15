# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from _utils import parse_yaml_dict  # pyright: ignore[reportImplicitRelativeImport]
from pydantic import ValidationError

from scansible.representations.ast import Block, ExtractionContext, Play, Playbook, Task
from scansible.representations.ast.nodes.playbook import PlayRoleRequirement
from scansible.utils import ProjectPath


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

    def rejects_play_with_empty_hosts():
        yaml = """
            name: test play
            hosts: []
            tasks:
                - import_tasks: hello
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError, match="cannot be empty"):
            _ = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

    def extracts_play_with_vars_prompt():
        yaml = """
            name: test play
            hosts: servers
            vars_prompt:
              - name: my_var
                prompt: Enter a value
                default: hello
            tasks:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert len(result.vars_prompt) == 1
        assert result.vars_prompt[0].name == "my_var"
        assert result.vars_prompt[0].prompt == "Enter a value"
        assert result.vars_prompt[0].default == "hello"

    @pytest.mark.parametrize(
        ["vars_files_value", "expected"],
        [
            pytest.param("a.yml", [["a.yml"]], id="bare string"),
            pytest.param(["a.yml", "b.yml"], [["a.yml"], ["b.yml"]], id="flat list"),
            pytest.param([["a.yml", "b.yml"]], [["a.yml", "b.yml"]], id="nested list"),
        ],
    )
    def normalizes_vars_files(vars_files_value: object, expected: list[list[str]]):
        ctx = ExtractionContext(False)

        result = Play.model_validate(
            {
                "name": "test play",
                "hosts": "servers",
                "tasks": [{"import_tasks": "test"}],
                "vars_files": vars_files_value,
            },
            context=ctx,
        )

        assert result.vars_files == expected

    def extracts_play_with_pre_and_post_tasks():
        yaml = """
            name: test play
            hosts: servers
            pre_tasks:
              - import_tasks: pre
            tasks:
              - import_tasks: test
            post_tasks:
              - import_tasks: post
            handlers:
              - name: restart x
                service:
                    name: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert len(result.pre_tasks) == 1
        assert len(result.post_tasks) == 1
        assert len(result.handlers) == 1

    def ignores_removed_accelerate_directive():
        yaml = """
            name: test play
            hosts: servers
            accelerate: yes
            tasks:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.hosts == ["servers"]

    def extracts_play_with_int_role():
        yaml = """
            name: test play
            hosts: servers
            roles:
              - 123
            tasks:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert len(result.roles) == 1
        assert result.roles[0].role == "123"

    def normalizes_single_gather_subset():
        yaml = """
            name: test play
            hosts: servers
            gather_subset: network
            tasks:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.gather_subset == ["network"]

    def normalizes_single_serial_value():
        yaml = """
            name: test play
            hosts: servers
            serial: 1
            tasks:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.serial == [1]

    def normalizes_single_vars_prompt():
        yaml = """
            name: test play
            hosts: servers
            vars_prompt:
                name: my_var
                prompt: Enter a value
                default: hello
            tasks:
              - import_tasks: test
        """
        ctx = ExtractionContext(False)

        result = Play.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert len(result.vars_prompt) == 1
        assert result.vars_prompt[0].name == "my_var"
        assert result.vars_prompt[0].prompt == "Enter a value"
        assert result.vars_prompt[0].default == "hello"


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
