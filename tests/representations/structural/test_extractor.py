# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import Callable

from pathlib import Path
from textwrap import dedent

import ansible.parsing.dataloader
import pytest
from pydantic import ValidationError
from pytest_describe import behaves_like

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

        result = ext.extract_variable_file(ProjectPath(tmp_path, "main.yml"))

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

        result = ext.extract_variable_file(ProjectPath(tmp_path, "main.yml"))

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

        result = ext.extract_variable_file(ProjectPath(tmp_path, "main.yml"))

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

        result = ext.extract_variable_file(ProjectPath(tmp_path, "main.yml"))

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
            _ = ext.extract_variable_file(ProjectPath(tmp_path, "main.yml"))


TaskExtractor = Callable[
    [dict[str, "ans.AnsibleValue"], ast.ExtractionContext],
    ast.Task | ast.Handler | None,
]


# Shared behaviour for task extractors
def a_task_extractor() -> None:
    def extracts_standard_task(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: Ensure file exists
            file:
                path: test.txt
                state: present
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "file"
        assert result.args == {"path": "test.txt", "state": "present"}
        assert result.name == "Ensure file exists"

    def extracts_standard_task_with_action_shorthand(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: Ensure file exists
            file: path=test.txt state=present
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "file"
        assert result.args == {"path": "test.txt", "state": "present"}
        assert result.name == "Ensure file exists"

    def extracts_task_with_vars(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            vars:
                file_path: test.txt
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "file"
        assert result.args == {"path": "{{ file_path }}"}
        assert result.name == "Ensure file exists"
        assert result.vars == {"file_path": "test.txt"}

    def extracts_task_with_loop(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            debug: msg={{ item }}
            loop: [hello, world]
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "debug"
        assert result.args == {"msg": "{{ item }}"}
        assert result.name == "test"
        assert result.loop == ["hello", "world"]

    def extracts_task_with_expr_loop(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            debug: msg={{ item }}
            loop: '{{ somelist }}'
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "debug"
        assert result.args == {"msg": "{{ item }}"}
        assert result.name == "test"
        assert result.loop == "{{ somelist }}"

    def extracts_task_with_loop_control(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            debug: msg={{ myvar }}
            loop: [hello, world]
            loop_control:
              loop_var: myvar
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "debug"
        assert result.args == {"msg": "{{ myvar }}"}
        assert result.name == "test"
        assert result.loop == ["hello", "world"]
        assert result.loop_control is not None
        assert result.loop_control.loop_var == "myvar"

    def extracts_task_with_literal_boolean_when(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            debug: msg={{ myvar }}
            when: yes
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "debug"
        assert result.args == {"msg": "{{ myvar }}"}
        assert result.name == "test"
        assert result.when == [True]

    def does_not_eagerly_evaluate_imports(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            import_tasks: tasks.yml
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "import_tasks"
        assert result.args == {"_raw_params": "tasks.yml"}

    @pytest.mark.xfail(
        reason="Broken in more recent Ansible versions, we need to reduce the reliance on Ansible for parsing"
    )
    def does_not_eagerly_evaluate_expressions(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        # register is a "static" field and Ansible will try to evaluate the
        # expression eagerly, which we should prevent
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            debug:
                msg: hello
            register: '{{ expr }}'
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "debug"
        assert result.args == {"msg": "hello"}
        assert result.name == "test"
        assert result.register == "{{ expr }}"

    def does_not_eagerly_resolve_actions(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            action_that_doesnt_exist:
                msg: hello
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "action_that_doesnt_exist"
        assert result.args == {"msg": "hello"}
        assert result.name == "test"

    def normalises_deprecated_with_keyword(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            file:
              path: '{{ item }}'
            with_items:
              - hello
              - world
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "file"
        assert result.args == {"path": "{{ item }}"}
        assert result.name == "test"
        assert result.loop == ["hello", "world"]
        assert result.loop_with == "items"

    def extracts_include_task(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            include: test.yml
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "include_tasks"
        assert result.args == {"_raw_params": "test.yml"}

    def extracts_include_static_task(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            include: test.yml
            static: yes
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "import_tasks"
        assert result.args == {"_raw_params": "test.yml"}

    def extracts_include_nonstatic_task(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            include: test.yml
            static: no
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "include_tasks"
        assert result.args == {"_raw_params": "test.yml"}

    def extracts_include_role_task(
        extractor: TaskExtractor, task_representation: type[ast.Task]
    ) -> None:
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            include_role:
                name: testrole
                public: true
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert isinstance(result, task_representation)
        assert result.action == "include_role"
        assert result.args == {"name": "testrole", "public": True}

    def rejects_tasks_with_invalid_attribute_values(extractor: TaskExtractor) -> None:
        with pytest.raises(Exception):
            _ = extractor(
                _parse_yaml_dict(
                    dedent(
                        """
                name: test
                file:
                    path: test.txt
                vars: 0
            """
                    )
                ),
                ast.ExtractionContext(False),
            )

    def rejects_tasks_with_invalid_postvalidated_attribute_values(
        extractor: TaskExtractor,
    ) -> None:
        with pytest.raises(Exception):
            _ = extractor(
                _parse_yaml_dict(
                    dedent(
                        """
                name: test
                file:
                    path: test.txt
                loop_control: 0
            """
                    )
                ),
                ast.ExtractionContext(False),
            )

    def rejects_tasks_with_no_action(extractor: TaskExtractor) -> None:
        with pytest.raises(Exception):
            _ = extractor(
                _parse_yaml_dict(
                    dedent(
                        """
                name: test
            """
                    )
                ),
                ast.ExtractionContext(False),
            )

    def rejects_tasks_with_multiple_actions(extractor: TaskExtractor) -> None:
        with pytest.raises(Exception):
            _ = extractor(
                _parse_yaml_dict(
                    dedent(
                        """
                name: test
                file:
                    path: test.txt
                apt:
                    name: test.txt
            """
                    )
                ),
                ast.ExtractionContext(False),
            )

    def ignores_malformed_task_in_lenient_mode(extractor: TaskExtractor) -> None:
        ctx = ast.ExtractionContext(True)
        result = extractor(
            _parse_yaml_dict(
                dedent(
                    """
            name: test
            file:
                path: test.txt
            apt:
                name: test.txt
        """
                )
            ),
            ctx,
        )

        assert result is None
        assert len(ctx.broken_tasks) == 1


@behaves_like(a_task_extractor)
def describe_extracting_tasks() -> None:

    @pytest.fixture()
    def extractor() -> TaskExtractor:
        return ext.extract_task

    @pytest.fixture()
    def task_representation() -> type[ast.Task]:
        return ast.Task


@behaves_like(a_task_extractor)
def describe_extracting_handlers() -> None:
    @pytest.fixture()
    def extractor() -> TaskExtractor:
        return ext.extract_handler

    @pytest.fixture()
    def task_representation() -> type[ast.Handler]:
        return ast.Handler

    def extracts_handler_with_listen() -> None:
        result = ext.extract_handler(
            _parse_yaml_dict(
                dedent(
                    """
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            listen: a topic
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result is not None
        assert result.action == "file"
        assert result.name == "Ensure file exists"
        assert result.args == {"path": "{{ file_path }}"}
        assert result.listen == ["a topic"]

    def extracts_handler_with_list_of_listens() -> None:
        result = ext.extract_handler(
            _parse_yaml_dict(
                dedent(
                    """
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            listen:
              - a topic
              - another topic
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result is not None
        assert result.action == "file"
        assert result.name == "Ensure file exists"
        assert result.args == {"path": "{{ file_path }}"}
        assert result.listen == ["a topic", "another topic"]


def describe_extracting_list_of_handlers() -> None:
    def extracts_as_handlers() -> None:
        result = ext.extract_list_of_tasks_or_blocks(
            _parse_yaml_list(
                dedent(
                    """
            - file: {}
            - apt: {}
        """
                )
            ),
            ast.ExtractionContext(False),
            handlers=True,
        )

        assert len(result) == 2
        assert isinstance(result[0], ast.Handler)
        assert isinstance(result[1], ast.Handler)


def describe_extracting_blocks() -> None:
    def extracts_standard_blocks() -> None:
        result = ext.extract_block(
            _parse_yaml_dict(
                dedent(
                    """
            block:
              - name: test
                file: {}
              - name: test2
                file: {}
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result is not None
        assert len(result.block) == 2
        assert isinstance(result.block[0], ast.Task)
        assert isinstance(result.block[1], ast.Task)
        assert result.block[0].name == "test"
        assert result.block[1].name == "test2"

    # def extracts_block_of_handlers() -> None:
    #     result = ext.extract_block(
    #         _parse_yaml_dict(
    #             dedent(
    #                 """
    #         block:
    #           - name: test
    #             file: {}
    #           - name: test2
    #             file: {}
    #     """
    #             )
    #         ),
    #         ast.ExtractionContext(False),
    #         handlers=True,
    #     )

    #     assert result is not None
    #     assert result == rep.Block(
    #         block=[
    #             rep.Handler(action="file", name="test", args={}, raw=None),
    #             rep.Handler(action="file", name="test2", args={}, raw=None),
    #         ],
    #         raw=None,
    #     )
    #     assert all(
    #         child.parent is result
    #         for child in chain(result.block, result.rescue, result.always)
    #     )

    def extracts_blocks_with_rescue_and_always() -> None:
        result = ext.extract_block(
            _parse_yaml_dict(
                dedent(
                    """
            block:
              - name: test
                file: {}
            rescue:
              - name: test2
                file: {}
            always:
              - name: test3
                file: {}
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result is not None
        assert len(result.block) == 1
        assert len(result.rescue) == 1
        assert len(result.always) == 1
        assert isinstance(result.block[0], ast.Task)
        assert isinstance(result.rescue[0], ast.Task)
        assert isinstance(result.always[0], ast.Task)
        assert result.block[0].name == "test"
        assert result.rescue[0].name == "test2"
        assert result.always[0].name == "test3"

    def extracts_nested_blocks() -> None:
        result = ext.extract_block(
            _parse_yaml_dict(
                dedent(
                    """
            block:
              - name: test
                file: {}
              - block:
                  - name: test
                    file: {}
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result is not None
        assert len(result.block) == 2
        assert isinstance(result.block[0], ast.Task)
        assert isinstance(result.block[1], ast.Block)
        assert result.block[0].name == "test"
        assert len(result.block[1].block) == 1
        assert isinstance(result.block[1].block[0], ast.Task)
        assert result.block[1].block[0].name == "test"

    def does_not_eagerly_load_import_tasks() -> None:
        result = ext.extract_block(
            _parse_yaml_dict(
                dedent(
                    """
            block:
              - import_tasks: test
        """
                )
            ),
            ast.ExtractionContext(False),
        )

        assert result is not None
        assert len(result.block) == 1
        assert isinstance(result.block[0], ast.Task)
        assert result.block[0].action == "import_tasks"

    def rejects_non_blocks() -> None:
        with pytest.raises(Exception):
            _ = ext.extract_block(
                _parse_yaml_dict(
                    dedent(
                        """
                import_tasks: test
            """
                    )
                ),
                ast.ExtractionContext(False),
            )

    def rejects_blocks_without_block() -> None:
        with pytest.raises(Exception):
            _ = ext.extract_block(
                _parse_yaml_dict(
                    dedent(
                        """
                rescue:
                  - file: {}
            """
                    )
                ),
                ast.ExtractionContext(False),
            )

    def ignores_malformed_block_in_lenient_mode() -> None:
        ctx = ast.ExtractionContext(True)

        result = ext.extract_block(
            _parse_yaml_dict(
                dedent(
                    """
            rescue:
              - file: {}
        """
                )
            ),
            ctx,
        )

        assert result is None
        assert len(ctx.broken_tasks) == 1


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
