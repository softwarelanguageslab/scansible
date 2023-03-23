from __future__ import annotations

from typing import TYPE_CHECKING, Any, Callable

from pathlib import Path

import pytest

if TYPE_CHECKING:
    from _pytest.capture import CaptureFixture

from scansible.representations.structural import ansible_types as ans
from scansible.representations.structural import helpers as h
from scansible.representations.structural import loaders
from scansible.representations.structural.loaders import LoadError

LoadMetaType = Callable[[str], tuple[dict[str, "ans.AnsibleValue"], Any]]
LoadVarsType = Callable[[str], tuple[dict[str, "ans.AnsibleValue"], Any]]
LoadTasksFileType = Callable[[str], tuple[list[dict[str, "ans.AnsibleValue"]], Any]]
LoadPlaybookType = Callable[[str], tuple[list[dict[str, "ans.AnsibleValue"]], Any]]


@pytest.fixture()
def load_meta(tmp_path: Path) -> LoadMetaType:
    def inner(yaml_content: str) -> tuple[dict[str, ans.AnsibleValue], Any]:
        (tmp_path / "main.yml").write_text(yaml_content)
        return loaders.load_role_metadata(h.ProjectPath(tmp_path, "main.yml"))

    return inner


@pytest.fixture()
def load_vars(tmp_path: Path) -> LoadVarsType:
    def inner(yaml_content: str) -> tuple[dict[str, ans.AnsibleValue], Any]:
        (tmp_path / "main.yml").write_text(yaml_content)
        return loaders.load_variable_file(h.ProjectPath(tmp_path, "main.yml"))

    return inner


@pytest.fixture()
def load_tasks_file(tmp_path: Path) -> LoadTasksFileType:
    def inner(yaml_content: str) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
        (tmp_path / "main.yml").write_text(yaml_content)
        return loaders.load_tasks_file(h.ProjectPath(tmp_path, "main.yml"))

    return inner


@pytest.fixture()
def load_pb(tmp_path: Path) -> LoadPlaybookType:
    def inner(yaml_content: str) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
        (tmp_path / "pb.yml").write_text(yaml_content)
        return loaders.load_playbook(h.ProjectPath(tmp_path, "pb.yml"))

    return inner


def describe_load_role_metadata() -> None:
    def loads_correct_metadata(load_meta: LoadMetaType) -> None:
        result = load_meta(
            """
            galaxy_info:
                name: test
                author: test
                platforms:
                  - name: Debian
                    versions:
                      - any
                      - all
                  - name: Fedora
                    versions:
                      - 9

            dependencies:
              - name: test
                when:
                  - x is True
                  - y is True
        """
        )

        assert result[0] == {
            "galaxy_info": {
                "name": "test",
                "author": "test",
                "platforms": [
                    {"name": "Debian", "versions": ["all"]},
                    {"name": "Fedora", "versions": ["9"]},
                ],
            },
            "dependencies": [
                {
                    "name": "test",
                    "when": ["x is True", "y is True"],
                }
            ],
        }

    def normalises_missing_galaxy_info_property(load_meta: LoadMetaType) -> None:
        result: tuple[Any, Any] = load_meta(
            """
                dependencies: []
            """
        )

        assert isinstance(result[0]["galaxy_info"], dict)
        assert "galaxy_info" not in result[1]

    def raises_on_empty_metadata(load_meta: LoadMetaType) -> None:
        with pytest.raises(LoadError, match="Empty metadata"):
            load_meta("")

    def raises_on_wrong_metadata_type(load_meta: LoadMetaType) -> None:
        with pytest.raises(LoadError, match="Expected role metadata to be dict"):
            load_meta("- test\n- test2")

    def raises_on_wrong_galaxy_info_type(load_meta: LoadMetaType) -> None:
        with pytest.raises(
            LoadError, match="Expected role metadata galaxy_info to be dict"
        ):
            load_meta(
                """
                galaxy_info:
                    - test
                    - test2
            """
            )

    def describe_loading_platforms() -> None:
        def normalises_missing_platforms_property(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                  name: test
                  author: test
                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == []
            assert "platforms" not in result[1]["galaxy_info"]

        def raises_on_wrong_platforms_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(
                LoadError,
                match="Expected role metadata galaxy_info.platforms to be list",
            ):
                load_meta(
                    """
                    galaxy_info:
                        platforms: Debian

                    dependencies: []
                """
                )

        def ignores_wrong_platform_type(
            load_meta: LoadMetaType, capsys: CaptureFixture[str]
        ) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - Debian

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == []
            captured = capsys.readouterr()
            assert "Ignoring malformed platform" in captured.out

        def ignores_missing_platform_name(
            load_meta: LoadMetaType, capsys: CaptureFixture[str]
        ) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - versions: [1, 2]

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == []
            captured = capsys.readouterr()
            assert "Ignoring malformed platform" in captured.out

        def inserts_default_platform_versions(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - name: Debian

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == [
                {"name": "Debian", "versions": ["all"]}
            ]

        def ignores_superfluous_platform_properties(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - name: Debian
                          versions:
                            - all
                          test: test

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == [
                {"name": "Debian", "versions": ["all"]}
            ]

        def stringifies_wrong_platform_name_type(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - name: 1
                          versions: ['v1', 'v2']

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == [
                {"name": "1", "versions": ["v1", "v2"]}
            ]

        def stringifies_non_string_platform_versions(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - name: Fedora
                          versions: [6, 7.1]

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == [
                {"name": "Fedora", "versions": ["6", "7.1"]}
            ]

        def does_likely_undesired_things_for_wrong_platform_versions_type(
            load_meta: LoadMetaType,
        ) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - name: Debian
                          versions: all

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == [
                {"name": "Debian", "versions": ["all"]}
            ]

        def reduces_versions_to_all_if_present(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - name: Debian
                          versions:
                            - any
                            - all

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == [
                {"name": "Debian", "versions": ["all"]}
            ]

        def ignores_wrong_versions_type(
            load_meta: LoadMetaType, capsys: CaptureFixture[str]
        ) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                    platforms:
                        - name: Debian
                          versions: xenial

                dependencies: []
            """
            )

            assert result[0]["galaxy_info"]["platforms"] == []
            captured = capsys.readouterr()
            assert "Ignoring malformed platform" in captured.out

    def describe_loading_dependencies() -> None:
        def normalises_missing_dependencies_property(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta(
                """
                galaxy_info:
                  name: test
                  author: test
                  platforms: []
            """
            )

            assert result[0]["dependencies"] == []
            assert "dependencies" not in result[1]

        def raises_on_wrong_dependencies_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(
                LoadError, match="Expected role dependencies to be list"
            ):
                load_meta(
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


def describe_load_variable_file() -> None:
    def loads_correct_file(load_vars: LoadVarsType) -> None:
        result = load_vars(
            """
            test: 123
            hello:
              x:
               - 1
               - b
              y: true
        """
        )

        assert result[0] == {
            "test": 123,
            "hello": {
                "x": [1, "b"],
                "y": True,
            },
        }

    def normalises_empty_file(load_vars: LoadVarsType) -> None:
        result, raw_result = load_vars("# just a comment")

        assert result == {}
        assert raw_result is None

    def raises_on_wrong_type(load_vars: LoadVarsType) -> None:
        with pytest.raises(LoadError, match="Expected variable file to be dict"):
            load_vars(
                """
                - a
                - b
            """
            )

    def raises_on_wrong_name_type(load_vars: LoadVarsType) -> None:
        with pytest.raises(LoadError, match="Expected variable name to be str"):
            load_vars(
                """
                1: 2
            """
            )


def describe_load_task_file() -> None:
    def loads_correct_file(load_tasks_file: LoadTasksFileType) -> None:
        result = load_tasks_file(
            """
            - name: test
              file: {}
            - block:
                - file: {}
        """
        )

        assert result[0] == [
            {
                "name": "test",
                "file": {},
            },
            {
                "block": [
                    {
                        "file": {},
                    }
                ]
            },
        ]

    def normalises_empty_file(load_tasks_file: LoadTasksFileType) -> None:
        result, raw_result = load_tasks_file("# just a comment")

        assert result == []
        assert raw_result is None

    def raises_on_wrong_type(load_tasks_file: LoadTasksFileType) -> None:
        with pytest.raises(LoadError, match="Expected task file to be list"):
            load_tasks_file(
                """
                a: 123
            """
            )

    def raises_on_wrong_property_type(load_tasks_file: LoadTasksFileType) -> None:
        with pytest.raises(
            LoadError,
            match=r"Expected task file content to be dict\[str, typing\.Any\]",
        ):
            load_tasks_file(
                """
                - 1: 2
            """
            )


def describe_load_task() -> None:
    def loads_correct_task() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "file": {
                    "path": "test.txt",
                    "state": "present",
                },
                "when": "x is not None",
            },
            as_handler=False,
        )

        assert isinstance(result[0], ans.Task)
        assert result[0].action == "file"
        assert result[0].args == {"path": "test.txt", "state": "present"}
        assert result[0].when == ["x is not None"]

    def loads_correct_handler() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "file": {
                    "path": "test.txt",
                    "state": "present",
                },
                "when": "x is not None",
                "listen": "test",
            },
            as_handler=True,
        )

        assert isinstance(result[0], ans.Handler)
        assert result[0].action == "file"
        assert result[0].args == {"path": "test.txt", "state": "present"}
        assert result[0].when == ["x is not None"]
        assert result[0].listen == ["test"]

    def loads_correct_task_include() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "include_tasks": "test.yml",
                "when": "x is not None",
            },
            as_handler=False,
        )

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == "include_tasks"
        assert result[0].args == {"_raw_params": "test.yml"}
        assert result[0].when == ["x is not None"]

    def loads_correct_task_include_import() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "import_tasks": "test.yml",
                "when": "x is not None",
            },
            as_handler=False,
        )

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == "import_tasks"
        assert result[0].args == {"_raw_params": "test.yml"}
        assert result[0].when == ["x is not None"]

    def loads_correct_handler_include() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "include_tasks": "test.yml",
                "listen": "test",
            },
            as_handler=True,
        )

        assert isinstance(result[0], ans.HandlerTaskInclude)
        assert result[0].action == "include_tasks"
        assert result[0].args == {"_raw_params": "test.yml"}
        assert result[0].listen == ["test"]

    def loads_correct_role_include() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "include_role": {
                    "name": "test",
                    "tasks_from": "test.yml",
                },
            },
            as_handler=False,
        )

        assert isinstance(result[0], ans.IncludeRole)
        assert result[0].action == "include_role"
        assert result[0].args == {"name": "test", "tasks_from": "test.yml"}

    def transforms_static_include() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "include": "test.yml",
                "static": "yes",
            },
            as_handler=False,
        )

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == "import_tasks"
        assert result[0].args == {"_raw_params": "test.yml"}
        assert "include" in result[1]
        assert "static" in result[1]
        assert "import_tasks" not in result[1]

    def transforms_static_no_include() -> None:
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "include": "test.yml",
                "static": "no",
            },
            as_handler=False,
        )

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == "include_tasks"
        assert result[0].args == {"_raw_params": "test.yml"}
        assert "include" in result[1]
        assert "static" in result[1]
        assert "include_tasks" not in result[1]

    def transforms_none_when() -> None:
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "get_url": {
                    "url": "...",
                    "dest": "...",
                },
                "when": None,
            },
            as_handler=False,
        )

        assert result[0].when == []
        assert result[1]["when"] is None

    def transforms_always_run() -> None:
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "get_url": {
                    "url": "...",
                    "dest": "...",
                },
                "always_run": "yes",
            },
            as_handler=False,
        )

        assert result[0].check_mode is False
        assert result[1]["always_run"] == "yes"
        assert "check_mode" not in result[1]

    def describe_transforming_old_become() -> None:
        @pytest.mark.parametrize("method", ["su", "sudo"])
        def transforms_old_become(method: str) -> None:
            ds = {
                "file": {},
                f"{method}": "yes",
                f"{method}_user": "me",
                f"{method}_exe": "test",
                f"{method}_flags": "--flag",
                f"{method}_pass": "sekrit",
            }
            result = loaders.load_task(ds, as_handler=False)  # type: ignore[call-overload]

            assert result[0].action == "file"
            assert result[0].become is True
            assert result[0].become_user == "me"
            assert result[0].become_exe == "test"
            assert result[0].become_flags == "--flag"
            assert result[0].vars == {"ansible_become_password": "sekrit"}
            assert result[1] == ds

        @pytest.mark.parametrize("method", ["su", "sudo"])
        def transforms_old_become_with_multiple_vars(method: str) -> None:
            ds = {
                "file": {},
                f"{method}": "yes",
                f"{method}_user": "me",
                f"{method}_exe": "test",
                f"{method}_flags": "--flag",
                f"{method}_pass": "sekrit",
                "vars": {
                    "other": "hello",
                },
            }
            result = loaders.load_task(ds, as_handler=False)  # type: ignore[call-overload]

            assert result[0].action == "file"
            assert result[0].become is True
            assert result[0].become_user == "me"
            assert result[0].become_exe == "test"
            assert result[0].become_flags == "--flag"
            assert result[0].vars == {
                "other": "hello",
                "ansible_become_password": "sekrit",
            }
            assert result[1] == ds

        @pytest.mark.parametrize(
            "combo", [("su", "sudo"), ("sudo", "become"), ("su", "become")]
        )
        def rejects_duplicate_become_method(combo: tuple[str, str]) -> None:
            with pytest.raises(LoadError, match="Invalid mix of directives"):
                loaders.load_task(
                    {  # type: ignore[call-overload]
                        "file": {},
                        combo[0]: "yes",
                        combo[1]: "yes",
                    },
                    as_handler=False,
                )

    def transforms_become() -> None:
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        result = loaders.load_task(
            {  # type: ignore[call-overload]
                "get_url": {
                    "url": "...",
                    "dest": "...",
                },
                "when": None,
            },
            as_handler=False,
        )

        assert result[0].when == []
        assert result[1]["when"] is None


def describe_load_block() -> None:
    def loads_correct_block() -> None:
        result = loaders.load_block(
            {
                "block": [{"file": {}}],  # type: ignore[dict-item]
                "rescue": [{"file": {}}],  # type: ignore[dict-item]
            }
        )

        assert result[0].block == [{"file": {}}]
        assert result[0].rescue == [{"file": {}}]
        assert result[0].always == []

    def raises_if_not_a_block() -> None:
        with pytest.raises(LoadError, match="Not a block"):
            loaders.load_block({"file": {}})  # type: ignore[dict-item]


def describe_load_play() -> None:
    def loads_correct_play() -> None:
        result = loaders.load_play(
            {
                "hosts": "hello",  # type: ignore[dict-item]
                "tasks": [],  # type: ignore[dict-item]
            }
        )

        assert result[0].hosts == ["hello"]
        assert result[0].tasks == []


def describe_load_playbook() -> None:
    def loads_correct_playbook(load_pb: LoadPlaybookType) -> None:
        result = load_pb(
            """---
            - hosts: servers
              name: x
              tasks: []
            - hosts: databases
              name: x
              tasks: []
        """
        )

        assert result[0] == [
            {
                "hosts": "servers",
                "name": "x",
                "tasks": [],
            },
            {
                "hosts": "databases",
                "name": "x",
                "tasks": [],
            },
        ]

    def raises_on_empty_playbook(load_pb: LoadPlaybookType) -> None:
        with pytest.raises(LoadError, match="Empty playbook"):
            load_pb("# just a comment")

    def raises_on_wrong_type(load_pb: LoadPlaybookType) -> None:
        with pytest.raises(LoadError, match="Expected playbook to be list"):
            load_pb(
                """
                hosts: x
                name: test
            """
            )


def describe_load_role_dependency() -> None:
    def normalises_dependency_without_condition() -> None:
        result: tuple[
            ans.role.RoleInclude, dict[str, str] | None, Any
        ] = loaders.load_role_dependency(
            {"role": "test"}  # type: ignore[dict-item]
        )

        assert result[0].role == "test"
        assert result[0].when == []
        assert result[1] is None
        assert result[2] == {"role": "test"}

    def normalises_dependency_with_single_condition() -> None:
        result: tuple[
            ans.role.RoleInclude, dict[str, str] | None, Any
        ] = loaders.load_role_dependency(
            {
                "role": "test",  # type: ignore[dict-item]
                "when": "x is True",  # type: ignore[dict-item]
            }
        )

        assert result[0].role == "test"
        assert result[0].when == ["x is True"]
        assert result[1] is None

    def normalises_bare_string_dependency() -> None:
        result: tuple[
            ans.role.RoleInclude, dict[str, str] | None, Any
        ] = loaders.load_role_dependency("test")

        assert result[0].role == "test"
        assert result[0].when == []
        assert result[1] is None
        assert result[2] == "test"

    def normalises_dependency_with_name_instead_of_role() -> None:
        result: tuple[
            ans.role.RoleInclude, dict[str, str] | None, Any
        ] = loaders.load_role_dependency(
            {"name": "test"}  # type: ignore[dict-item]
        )

        assert result[0].role == "test"
        assert result[0].when == []
        assert result[1] is None
        assert result[2] == {"name": "test"}

    def normalises_int_role_name_to_str() -> None:
        result: tuple[ans.role.RoleInclude, dict[str, str] | None, Any] = loaders.load_role_dependency(123)  # type: ignore[arg-type]

        assert result[0].role == "123"
        assert result[1] is None
        assert result[2] == 123

    def raises_on_wrong_dependency_type() -> None:
        with pytest.raises(
            LoadError, match=r"Expected role dependency to be str \| dict"
        ):
            loaders.load_role_dependency(["hello", "world"])  # type: ignore[arg-type]

    def raises_on_missing_dependency_name() -> None:
        with pytest.raises(
            ans.AnsibleError, match="role definitions must contain a role name"
        ):
            loaders.load_role_dependency({"when": "yes"})  # type: ignore[dict-item]

    def raises_on_invalid_role_name_type() -> None:
        with pytest.raises(
            ans.AnsibleError, match="role definitions must contain a role name"
        ):
            loaders.load_role_dependency({"role": ["abc"]})  # type: ignore[dict-item]

    def considers_superfluous_non_directive_dependency_properties_to_be_parameters() -> None:
        result: tuple[
            ans.role.RoleInclude, dict[str, str] | None, Any
        ] = loaders.load_role_dependency(
            {
                "role": "test",  # type: ignore[dict-item]
                "param_x": 123,
                "become": "yes",  # type: ignore[dict-item]
            }
        )

        assert result[0].role == "test"
        assert result[0].become == True
        assert result[0]._role_params == {"param_x": 123}

    def loads_new_style_role_requirements() -> None:
        result: tuple[
            ans.role.RoleInclude, dict[str, str] | None, Any
        ] = loaders.load_role_dependency(
            {
                "src": "https://github.com/bennojoy/nginx",  # type: ignore[dict-item]
                "version": "main",  # type: ignore[dict-item]
            },
            allow_new_style=True,
        )

        assert result[0].role == "nginx"
        assert result[1] == {
            "name": "nginx",
            "src": "https://github.com/bennojoy/nginx",
            "version": "main",
            "scm": "git",
        }
