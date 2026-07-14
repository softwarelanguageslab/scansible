# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import ansible.parsing.dataloader
import pytest
from pydantic import ValidationError

from scansible.representations.structural import ansible_types as ans
from scansible.representations.structural import ast
from scansible.representations.structural import extractor as ext
from scansible.representations.structural.helpers import ProjectPath
from scansible.types import VaultValue


def _parse_yaml_dict(yaml_content: str) -> dict[str, ans.AnsibleValue]:
    loader = ansible.parsing.dataloader.DataLoader()
    result = loader.load(data=yaml_content)
    assert isinstance(result, dict)
    return result


def _parse_yaml_list(yaml_content: str) -> list[dict[str, ans.AnsibleValue]]:
    loader = ansible.parsing.dataloader.DataLoader()
    result = loader.load(data=yaml_content)
    assert isinstance(result, list)
    return result


def describe_extracting_metadata_file() -> None:
    def rejects_empty_metadata(tmp_path: Path) -> None:
        _ = (tmp_path / "main.yml").write_text("")

        with pytest.raises(Exception):
            _ = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

    @pytest.mark.parametrize("content", ["- hello\n- world"])  # list  # string
    def rejects_invalid_files(tmp_path: Path, content: str) -> None:
        _ = (tmp_path / "main.yml").write_text(content)

        with pytest.raises(Exception):
            _ = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

    def describe_platforms() -> None:
        def extracts_standard_platforms_without_dependencies(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies: []

                galaxy_info:
                    role_name: test
                    author: test
                    platforms:
                        - name: Debian
                          versions:
                            - any
                        - name: Fedora
                          versions:
                            - 7
                            - 8
                """
                )
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert result.path == Path("main.yml")
            assert len(result.metablock.platforms) == 3
            assert result.metablock.platforms[0].name == "Debian"
            assert result.metablock.platforms[0].version == "any"
            assert result.metablock.platforms[1].name == "Fedora"
            assert result.metablock.platforms[1].version == "7"
            assert result.metablock.platforms[2].name == "Fedora"
            assert result.metablock.platforms[2].version == "8"
            assert not result.metablock.platforms[0].position.is_synthetic
            assert result.metablock.platforms[0].position.start_line == 8
            assert not result.metablock.dependencies

        def normalises_missing_platforms_property(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                galaxy_info:
                  name: test
                  author: test
                dependencies: []
            """
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert not result.metablock.platforms

        def rejects_invalid_galaxy_info(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                galaxy_info:
                    - test
                    - test2
            """
                )
            )

            with pytest.raises(Exception):
                _ = ext.extract_role_metadata_file(
                    ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
                )

        def rejects_invalid_platforms_list(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                galaxy_info:
                    platforms: yes
            """
                )
            )

            with pytest.raises(Exception):
                _ = ext.extract_role_metadata_file(
                    ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
                )

        def rejects_weird_platform_entry(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                galaxy_info:
                    platforms:
                    - [hello]
            """
                )
            )

            with pytest.raises(ValidationError):
                _ = ext.extract_role_metadata_file(
                    ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
                )

        def normalises_missing_galaxy_info_property(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    dependencies: []
                """
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert not result.metablock.platforms

    def describe_dependencies() -> None:
        def extracts_simple_string_dependencies(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies:
                    - testrole
            """
                )
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"

        def extracts_simple_dict_dependencies_with_role_key(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies:
                    - role: testrole
            """
                )
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"

        def normalises_int_role_name_to_str(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies:
                    - 123
            """
                )
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "123"

        def extracts_simple_dict_dependencies_with_name_key(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies:
                    - name: testrole
            """
                )
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].name == "testrole"
            assert result.metablock.dependencies[0].role == "testrole"

        def extracts_dependencies_with_condition(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies:
                    - role: testrole
                      when: "{{ ansible_os_family == 'Debian' }}"
            """
                )
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"
            assert result.metablock.dependencies[0].when == [
                "{{ ansible_os_family == 'Debian' }}"
            ]

        def extracts_dependencies_with_multiple_conditions(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies:
                    - role: testrole
                      when:
                        - "{{ ansible_os_family == 'Debian' }}"
                        - "{{ 1 + 1 == 2 }}"
            """
                )
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"
            assert result.metablock.dependencies[0].when == [
                "{{ ansible_os_family == 'Debian' }}",
                "{{ 1 + 1 == 2 }}",
            ]

        def ignores_malformed_dependency_in_lenient_mode(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                dedent(
                    """
                dependencies:
                    - test: nope
            """
                )
            )
            ctx = ast.ExtractionContext(True)

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ctx
            )

            assert result.metablock.dependencies == []
            assert ctx.broken_tasks[0].raw == {"test": "nope"}

        def normalises_missing_dependencies_property(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                galaxy_info:
                  name: test
                  author: test
                  platforms: []
            """
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert not result.metablock.dependencies

        def raises_on_wrong_dependencies_type(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        test: x
                """
            )

            with pytest.raises(Exception):
                _ = ext.extract_role_metadata_file(
                    ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
                )

        def raises_on_wrong_dependency_type(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - [a, b]
                """
            )

            with pytest.raises(Exception):
                _ = ext.extract_role_metadata_file(
                    ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
                )

        def raises_on_missing_role_name(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - when: x is True
                """
            )

            with pytest.raises(Exception):
                _ = ext.extract_role_metadata_file(
                    ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
                )

        def raises_on_invalid_role_name_type(tmp_path: Path) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - name: [not, a, string]
                """
            )

            with pytest.raises(Exception):
                _ = ext.extract_role_metadata_file(
                    ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
                )

        def considers_extra_non_directive_dependency_properties_to_be_parameters(
            tmp_path: Path,
        ) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - role: test
                          become: yes
                          param_x: 123
                """
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "test"
            assert result.metablock.dependencies[0].become is True
            assert result.metablock.dependencies[0].params == {"param_x": 123}

        def supports_new_style_role_requirements(
            tmp_path: Path,
        ) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - src: https://github.com/bennojoy/nginx
                          version: main
                """
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "nginx"

        def supports_string_based_new_style_role_requirements(
            tmp_path: Path,
        ) -> None:
            _ = (tmp_path / "main.yml").write_text(
                """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - git+https://github.com/bennojoy/nginx,main,testrole
                """
            )

            result = ext.extract_role_metadata_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"


def describe_extracting_variables() -> None:
    def extracts_simple_variables(tmp_path: Path) -> None:
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                """
            test: hello world
            test2: 123
            test3:
                - hello
                - world
            test4:
                this: is
                a: dict
        """
            )
        )

        result = ext.extract_variable_file(
            ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
        )

        assert result.path == Path("main.yml")
        assert result.variables == {
            "test": "hello world",
            "test2": 123,
            "test3": ["hello", "world"],
            "test4": {"this": "is", "a": "dict"},
        }

    def extracts_vault_variables(tmp_path: Path) -> None:
        # ioannis1/pg_config/defaults/main.yml
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                """
            postgres_passwd:     !vault |
                $ANSIBLE_VAULT;1.1;AES256
                62396263313762316136336334303463366465303638626438616530343935623766626534366436
        """
            )
        )

        result = ext.extract_variable_file(
            ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
        )

        assert result.path == Path("main.yml")
        assert result.variables == {
            "postgres_passwd": VaultValue(
                data=b"$ANSIBLE_VAULT;1.1;AES256\n62396263313762316136336334303463366465303638626438616530343935623766626534366436\n",
                ansible_pos=(f"{tmp_path}/main.yml", 2, 22),
            ),
        }

    def allows_variable_values_to_be_none(tmp_path: Path) -> None:
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                """
            test:
        """
            )
        )

        result = ext.extract_variable_file(
            ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
        )

        assert result.path == Path("main.yml")
        assert result.variables == {"test": None}

    def allows_variable_files_to_be_empty(tmp_path: Path) -> None:
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                """
            # just a comment
        """
            )
        )

        result = ext.extract_variable_file(
            ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
        )

        assert result.path == Path("main.yml")
        assert result.variables == {}

    @pytest.mark.parametrize(
        "content",
        [
            "- hello\n- world",  # list instead of dict
            "test123",  # string instead of dict
            "1: 2\nabc: def",  # non-string keys.
        ],
    )
    def rejects_invalid_files(tmp_path: Path, content: str) -> None:
        _ = (tmp_path / "main.yml").write_text(content)

        with pytest.raises(ValidationError):
            _ = ext.extract_variable_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

    @pytest.mark.parametrize(
        "identifier",
        ["123test", "un¡code™", "def", "for"],
    )
    def rejects_invalid_identifiers(tmp_path: Path, identifier: str) -> None:
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                f"""
            {identifier}: 123
        """
            )
        )

        with pytest.raises(ValidationError):
            _ = ext.extract_variable_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )


def describe_extracting_tasks_file() -> None:
    def extracts_standard_task_files(tmp_path: Path) -> None:
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                """
            - name: hello world
              file:
                path: hello
            - block:
                - name: test
                  test: {}
        """
            )
        )

        result = ext.extract_tasks_file(
            ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
        )

        assert result.path == Path("main.yml")
        assert len(result.tasks) == 2
        assert isinstance(result.tasks[0], ast.Task)
        assert isinstance(result.tasks[1], ast.Block)

    def allows_task_files_to_be_empty(tmp_path: Path) -> None:
        _ = (tmp_path / "main.yml").write_text("# just a comment")

        result = ext.extract_tasks_file(
            ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
        )

        assert result.path == Path("main.yml")
        assert not result.tasks

    @pytest.mark.parametrize("content", ["hello: world"])  # dict  # string
    def rejects_invalid_files(tmp_path: Path, content: str) -> None:
        _ = (tmp_path / "main.yml").write_text(content)

        with pytest.raises(Exception):
            _ = ext.extract_tasks_file(
                ProjectPath(tmp_path, "main.yml"), ast.ExtractionContext(False)
            )

    def ignores_malformed_task_in_lenient_mode(tmp_path: Path) -> None:
        ctx = ast.ExtractionContext(True)
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                """
            - name: test
              file:
                path: test.txt
              apt:
                name: test.txt
        """
            )
        )

        result = ext.extract_tasks_file(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.tasks) == 0
        assert len(ctx.broken_tasks) == 1

    def ignores_malformed_block_in_lenient_mode(tmp_path: Path) -> None:
        ctx = ast.ExtractionContext(True)
        _ = (tmp_path / "main.yml").write_text(
            dedent(
                """
            - rescue:
                - file: {}
        """
            )
        )

        result = ext.extract_tasks_file(ProjectPath(tmp_path, "main.yml"), ctx)

        assert result.path == Path("main.yml")
        assert len(result.tasks) == 0
        assert len(ctx.broken_tasks) == 1


def describe_extracting_plays() -> None:
    def extracts_simple_play() -> None:
        result = ext.extract_play(
            _parse_yaml_dict(
                dedent(
                    """
            name: test play
            hosts: servers
            tasks:
              - import_tasks: test
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.tasks) == 1
        assert isinstance(result.tasks[0], ast.Task)

    def extracts_play_with_block() -> None:
        result = ext.extract_play(
            _parse_yaml_dict(
                dedent(
                    """
            name: test play
            hosts: servers
            tasks:
              - block:
                - import_tasks: test
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.tasks) == 1
        assert isinstance(result.tasks[0], ast.Block)

    def extracts_play_with_vars() -> None:
        result = ext.extract_play(
            _parse_yaml_dict(
                dedent(
                    """
            name: test play
            hosts: servers
            tasks:
              - import_tasks: test
            vars:
              testvar: 123
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.tasks) == 1
        assert isinstance(result.tasks[0], ast.Task)
        assert result.vars == {"testvar": 123}

    def extracts_play_with_roles() -> None:
        result = ext.extract_play(
            _parse_yaml_dict(
                dedent(
                    """
            name: test play
            hosts: servers
            roles:
              - testrole
            tasks:
              - import_tasks: test
            vars:
              testvar: 123
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result.hosts == ["servers"]
        assert result.name == "test play"
        assert len(result.roles) == 1
        assert isinstance(result.roles[0], ast.PlayRoleRequirement)
        assert result.roles[0].role == "testrole"
        assert result.vars == {"testvar": 123}

    def rejects_invalid_play() -> None:
        with pytest.raises(Exception):
            # missing hosts
            _ = ext.extract_play(
                _parse_yaml_dict(
                    dedent(
                        """
                name: test play
                tasks:
                  - import_tasks: hello
            """
                    )
                ),
                ast.ExtractionContext(False),
            )


def describe_extract_playbook() -> None:
    def extracts_correct_playbook(tmp_path: Path) -> None:
        pb_content = dedent(
            """
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
        )
        _ = (tmp_path / "pb.yml").write_text(pb_content)

        result = ext.extract_playbook(tmp_path / "pb.yml")

        assert result.is_playbook
        assert not result.is_role
        assert result.path == tmp_path / "pb.yml"
        assert isinstance(result.root, ast.Playbook)
        assert result.root.path == Path("pb.yml")
        assert len(result.root.plays) == 1
        assert isinstance(result.root.plays[0], ast.Play)
        assert not result.root.broken_files
        assert not result.root.broken_tasks

    def extracts_playbooks_with_multiple_plays(tmp_path: Path) -> None:
        pb_content = dedent(
            """
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
        )
        _ = (tmp_path / "pb.yml").write_text(pb_content)

        result = ext.extract_playbook(tmp_path / "pb.yml")

        assert result.is_playbook
        assert not result.is_role
        assert result.path == tmp_path / "pb.yml"
        assert isinstance(result.root, ast.Playbook)
        assert result.root.path == Path("pb.yml")
        assert len(result.root.plays) == 2
        assert isinstance(result.root.plays[0], ast.Play)
        assert isinstance(result.root.plays[1], ast.Play)
        assert not result.root.broken_files
        assert not result.root.broken_tasks

    def rejects_empty_playbooks(tmp_path: Path) -> None:
        _ = (tmp_path / "pb.yml").write_text("")

        with pytest.raises(Exception):
            _ = ext.extract_playbook(tmp_path / "pb.yml")


def describe_extracting_roles() -> None:
    def extracts_correct_roles(tmp_path: Path) -> None:
        for dirname in ("meta", "tasks", "vars", "defaults", "handlers"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "meta" / "main.yml").write_text(
            dedent(
                """
            dependencies: []
            galaxy_info:
              name: test
              author: test
              platforms:
                - name: Debian
                  versions:
                    - all
        """
            )
        )
        _ = (tmp_path / "tasks" / "main.yml").write_text(
            dedent(
                """
            - file:
                path: hello
            - apt:
                name: test
        """
            )
        )
        _ = (tmp_path / "defaults" / "main.yml").write_text(
            dedent(
                """
            a: 123
        """
            )
        )
        _ = (tmp_path / "vars" / "main.yml").write_text(
            dedent(
                """
            b: 456
        """
            )
        )
        _ = (tmp_path / "handlers" / "main.yml").write_text(
            dedent(
                """
            - name: restart x
              service:
                name: test
        """
            )
        )

        result = ext.extract_role(tmp_path)

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, ast.Role)
        assert result.path == tmp_path
        assert result.root.path == Path(".")
        assert not result.root.broken_files
        assert not result.root.broken_tasks

        tf = result.root.main_tasks_file
        assert tf is not None
        assert len(result.root.task_files) == 1
        assert tf == result.root.task_files["main"]
        assert tf.path == Path("tasks/main.yml")
        assert len(tf.tasks) == 2
        assert isinstance(tf.tasks[0], ast.Task)
        assert isinstance(tf.tasks[1], ast.Task)
        assert tf.tasks[0].action == "file"
        assert tf.tasks[1].action == "apt"

        mf = result.root.meta_file
        assert mf is not None
        assert mf.path == Path("meta/main.yml")
        assert len(mf.metablock.platforms) == 1
        assert mf.metablock.platforms[0].name == "Debian"
        assert mf.metablock.platforms[0].version == "all"
        assert not mf.metablock.dependencies

        vf = result.root.main_vars_file
        assert vf is not None
        assert len(result.root.role_var_files) == 1
        assert vf == result.root.role_var_files["main"]
        assert vf.path == Path("vars/main.yml")
        assert vf.variables == {"b": 456}

        df = result.root.main_defaults_file
        assert df is not None
        assert len(result.root.default_var_files) == 1
        assert df == result.root.default_var_files["main"]
        assert df.path == Path("defaults/main.yml")
        assert df.variables == {"a": 123}

        hf = result.root.main_handlers_file
        assert hf is not None
        assert len(result.root.handler_files) == 1
        assert hf == result.root.handler_files["main"]
        assert hf.path == Path("handlers/main.yml")
        assert len(hf.handlers) == 1
        assert isinstance(hf.handlers[0], ast.Handler)
        assert hf.handlers[0].name == "restart x"

    def extracts_roles_with_files_missing(tmp_path: Path) -> None:
        for dirname in ("meta", "tasks", "vars", "defaults", "handlers"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "tasks" / "main.yml").write_text(
            dedent(
                """
            - file:
                path: hello
            - apt:
                name: test
        """
            )
        )
        _ = (tmp_path / "defaults" / "main.yml").write_text(
            dedent(
                """
            a: 123
        """
            )
        )

        result = ext.extract_role(tmp_path)

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, ast.Role)
        assert result.path == tmp_path
        assert result.root.path == Path(".")
        assert not result.root.broken_files
        assert not result.root.broken_tasks

        assert len(result.root.task_files) == 1
        assert len(result.root.default_var_files) == 1
        assert len(result.root.role_var_files) == 0
        assert len(result.root.handler_files) == 0
        assert result.root.meta_file is None
        assert result.root.main_tasks_file is not None
        assert result.root.main_defaults_file is not None
        assert result.root.main_vars_file is None
        assert result.root.main_handlers_file is None

    def extracts_roles_with_broken_files(tmp_path: Path) -> None:
        for dirname in ("meta", "tasks", "vars", "defaults", "handlers"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "tasks" / "main.yml").write_text(
            dedent(
                """
            file:
                path: hello
            apt:
                name: test
        """
            )
        )
        _ = (tmp_path / "defaults" / "main.yml").write_text(
            dedent(
                """
            a: 123
        """
            )
        )

        result = ext.extract_role(tmp_path)

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, ast.Role)
        assert result.path == tmp_path
        assert result.root.path == Path(".")
        assert not result.root.broken_tasks

        assert len(result.root.task_files) == 0
        assert len(result.root.default_var_files) == 1
        assert len(result.root.role_var_files) == 0
        assert len(result.root.handler_files) == 0
        assert result.root.meta_file is None
        assert result.root.main_tasks_file is None
        assert result.root.main_defaults_file is not None
        assert result.root.main_vars_file is None
        assert result.root.main_handlers_file is None

        assert len(result.root.broken_files) == 1
        assert result.root.broken_files[0].path == Path("tasks/main.yml")

    def extracts_roles_with_non_main_files(tmp_path: Path) -> None:
        for dirname in ("meta", "tasks", "vars", "defaults", "handlers"):
            (tmp_path / dirname).mkdir()
        _ = (tmp_path / "tasks" / "main.yml").write_text(
            dedent(
                """
            - file:
                path: hello
            - import_tasks: other.yml
        """
            )
        )
        _ = (tmp_path / "tasks" / "other.yml").write_text(
            dedent(
                """
            - apt:
                name: test
        """
            )
        )

        _ = (tmp_path / "defaults" / "main.yml").write_text(
            dedent(
                """
            a: 123
        """
            )
        )

        result = ext.extract_role(tmp_path, extract_all=True)

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, ast.Role)
        assert result.path == tmp_path
        assert result.root.path == Path(".")
        assert not result.root.broken_files
        assert not result.root.broken_tasks

        assert len(result.root.task_files) == 2
        assert len(result.root.default_var_files) == 1
        assert len(result.root.role_var_files) == 0
        assert len(result.root.handler_files) == 0
        assert result.root.meta_file is None
        assert result.root.main_tasks_file == result.root.task_files["main"]
        assert result.root.main_defaults_file is not None
        assert result.root.main_vars_file is None
        assert result.root.main_handlers_file is None

        assert "other" in result.root.task_files
        other = result.root.task_files["other"]
        assert other.path == Path("tasks/other.yml")
        assert len(other.tasks) == 1
        assert isinstance(other.tasks[0], ast.Task)
        assert other.tasks[0].action == "apt"
