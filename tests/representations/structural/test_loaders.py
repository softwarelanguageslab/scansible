# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from collections.abc import Callable
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


# shorthand for cast
def _as_ansible(obj: dict[str, Any]) -> dict[str, ans.AnsibleValue]:
    return obj


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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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

            assert isinstance(result[0]["galaxy_info"], dict)
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


def describe_get_task_action() -> None:
    # Yes, all of these are legal :exploding_head:
    @pytest.mark.parametrize(
        ["task", "expected_action"],
        [
            pytest.param(
                {"debug": {"msg": "hi"}},
                "debug",
                id="module name with args dict",
            ),
            pytest.param(
                {"debug": {"msg": "hi"}, "name": "", "when": ["x"], "vars": {}},
                "debug",
                id="module name with args dict and additional task directives",
            ),
            pytest.param(
                {"debug": "msg=hi"},
                "debug",
                id="module name with k=v args",
            ),
            pytest.param(
                {"shell": "echo hi"},
                "shell",
                id="module name with freeform args",
            ),
            pytest.param(
                {"shell": "echo hi", "args": {"chdir": "/tmp"}},
                "shell",
                id="module name with freeform and structured args",
            ),
            pytest.param(
                {"ping": None},
                "ping",
                id="module name without args",
            ),
            pytest.param(
                {"action": "debug msg=hi"},
                "debug",
                id="legacy action form with k=v args",
            ),
            pytest.param(
                {"action": "shell echo hi"},
                "shell",
                id="legacy action form with freeform args",
            ),
            pytest.param(
                {"action": "ping"},
                "ping",
                id="legacy action form without args",
            ),
            pytest.param(
                {"local_action": "shell echo hi"},
                "shell",
                id="legacy local_action form with freeform args",
            ),
            pytest.param(
                {"local_action": "debug msg=hi"},
                "debug",
                id="legacy local_action form with k=v args",
            ),
            pytest.param(
                {"action": "debug", "args": {"msg": "hi"}},
                "debug",
                id="legacy action form with top-level structured args",
            ),
            pytest.param(
                {"action": {"module": "debug", "args": {"msg": "hi"}}},
                "debug",
                id="legacy action form with nested dict",
            ),
            pytest.param(
                {"action": {"module": "debug", "msg": "hi"}},
                "debug",
                id="legacy action form with nested dict and flat args",
            ),
            # Special cases
            pytest.param(
                {"include": "test.yml", "static": True},
                "include",
                id="include with static directive",
            ),
        ],
    )
    def loads_correct_action(
        task: dict[str, ans.AnsibleValue], expected_action: str
    ) -> None:
        action = loaders.get_task_action(task)

        assert action == expected_action

    @pytest.mark.parametrize(
        ["task"],
        [
            pytest.param(
                {"debug": {"msg": "hi"}, "file": {"path": "..."}},
                id="mixing multiple module names",
            ),
            pytest.param(
                {"debug": {"msg": "hi"}, "action": "shell echo hi"},
                id="mixing action and module names",
            ),
            pytest.param(
                {"debug": {"msg": "hi"}, "local_action": "shell echo hi"},
                id="mixing local_action and module names",
            ),
            pytest.param(
                {"action": "shell echo hi", "local_action": "shell echo hi"},
                id="mixing local_action and action",
            ),
            pytest.param(
                {"name": "", "when": ["x"], "vars": {}},
                id="no action",
            ),
            pytest.param(
                {"action": ["debug msg=hi", "file path=..."]},
                id="malformed action",
            ),
            pytest.param(
                {"local_action": ["debug msg=hi", "file path=..."]},
                id="malformed local_action",
            ),
        ],
    )
    def rejects_invalid_actions(task: dict[str, ans.AnsibleValue]) -> None:
        with pytest.raises(LoadError):
            _ = loaders.get_task_action(task)


def describe_load_task() -> None:
    def loads_correct_task() -> None:
        task_ds = _as_ansible(
            {
                "file": {
                    "path": "test.txt",
                    "state": "present",
                },
                "when": "x is not None",
            },
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert isinstance(result, ans.Task)
        assert result.action == "file"
        assert result.args == {"path": "test.txt", "state": "present"}
        assert result.when == ["x is not None"]
        assert orig_ds == task_ds

    def loads_correct_handler() -> None:
        handler_ds = _as_ansible(
            {
                "file": {
                    "path": "test.txt",
                    "state": "present",
                },
                "when": "x is not None",
                "listen": "test",
            }
        )

        result, orig_ds = loaders.load_task(handler_ds, as_handler=True)

        assert isinstance(result, ans.Handler)
        assert result.action == "file"
        assert result.args == {"path": "test.txt", "state": "present"}
        assert result.when == ["x is not None"]
        assert result.listen == ["test"]
        assert orig_ds == handler_ds

    def loads_correct_task_include() -> None:
        task_ds = _as_ansible(
            {
                "include_tasks": "test.yml",
                "when": "x is not None",
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert isinstance(result, ans.TaskInclude)
        assert result.action == "include_tasks"
        assert result.args == {"_raw_params": "test.yml"}
        assert result.when == ["x is not None"]
        assert orig_ds == task_ds

    def loads_correct_task_include_import() -> None:
        task_ds = _as_ansible(
            {
                "import_tasks": "test.yml",
                "when": "x is not None",
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert isinstance(result, ans.TaskInclude)
        assert result.action == "import_tasks"
        assert result.args == {"_raw_params": "test.yml"}
        assert result.when == ["x is not None"]
        assert orig_ds == task_ds

    def loads_correct_handler_include() -> None:
        task_ds = _as_ansible(
            {
                "include_tasks": "test.yml",
                "listen": "test",
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=True)

        assert isinstance(result, ans.HandlerTaskInclude)
        assert result.action == "include_tasks"
        assert result.args == {"_raw_params": "test.yml"}
        assert result.listen == ["test"]
        assert orig_ds == task_ds

    def loads_correct_role_include() -> None:
        task_ds = _as_ansible(
            {
                "include_role": {
                    "name": "test",
                    "tasks_from": "test.yml",
                },
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert isinstance(result, ans.IncludeRole)
        assert result.action == "include_role"
        assert result.args == {"name": "test", "tasks_from": "test.yml"}
        assert orig_ds == task_ds

    def transforms_static_include() -> None:
        task_ds = _as_ansible(
            {
                "include": "test.yml",
                "static": "yes",
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert isinstance(result, ans.TaskInclude)
        assert result.action == "import_tasks"
        assert result.args == {"_raw_params": "test.yml"}
        assert orig_ds == task_ds

    def transforms_static_no_include() -> None:
        task_ds = _as_ansible(
            {
                "include": "test.yml",
                "static": "no",
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert isinstance(result, ans.TaskInclude)
        assert result.action == "include_tasks"
        assert result.args == {"_raw_params": "test.yml"}
        assert orig_ds == task_ds

    def transforms_none_when() -> None:
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        task_ds = _as_ansible(
            {
                "get_url": {
                    "url": "...",
                    "dest": "...",
                },
                "when": None,
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert result.when == []
        assert orig_ds == task_ds

    def transforms_always_run() -> None:
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        task_ds = _as_ansible(
            {
                "get_url": {
                    "url": "...",
                    "dest": "...",
                },
                "always_run": "yes",
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert result.check_mode is False
        assert orig_ds == task_ds

    def describe_transforming_old_become() -> None:
        @pytest.mark.parametrize("method", ["su", "sudo"])
        def transforms_old_become(method: str) -> None:
            ds = _as_ansible(
                {
                    "file": {},
                    f"{method}": "yes",
                    f"{method}_user": "me",
                    f"{method}_exe": "test",
                    f"{method}_flags": "--flag",
                    f"{method}_pass": "sekrit",
                }
            )

            result, orig_ds = loaders.load_task(ds, as_handler=False)

            assert result.action == "file"
            assert result.become is True
            assert result.become_user == "me"
            assert result.become_exe == "test"
            assert result.become_flags == "--flag"
            assert result.vars == {"ansible_become_password": "sekrit"}
            assert orig_ds == ds

        @pytest.mark.parametrize("method", ["su", "sudo"])
        def transforms_old_become_with_multiple_vars(method: str) -> None:
            ds = _as_ansible(
                {
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
            )

            result, orig_ds = loaders.load_task(ds, as_handler=False)

            assert result.action == "file"
            assert result.become is True
            assert result.become_user == "me"
            assert result.become_exe == "test"
            assert result.become_flags == "--flag"
            assert result.vars == {
                "other": "hello",
                "ansible_become_password": "sekrit",
            }
            assert orig_ds == ds

        @pytest.mark.parametrize(
            "combo", [("su", "sudo"), ("sudo", "become"), ("su", "become")]
        )
        def rejects_duplicate_become_method(combo: tuple[str, str]) -> None:
            with pytest.raises(LoadError, match="Invalid mix of directives"):
                task_ds = _as_ansible(
                    {
                        "file": {},
                        combo[0]: "yes",
                        combo[1]: "yes",
                    }
                )
                loaders.load_task(task_ds, as_handler=False)

    def transforms_become() -> None:
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        task_ds = _as_ansible(
            {
                "get_url": {
                    "url": "...",
                    "dest": "...",
                },
                "when": None,
            }
        )

        result, orig_ds = loaders.load_task(task_ds, as_handler=False)

        assert result.when == []
        assert orig_ds["when"] is None


def describe_load_block() -> None:
    def loads_correct_block() -> None:
        block_ds = _as_ansible(
            {
                "block": [{"file": {}}],
                "rescue": [{"file": {}}],
            }
        )

        result, orig_ds = loaders.load_block(block_ds)

        assert result.block == [{"file": {}}]
        assert result.rescue == [{"file": {}}]
        assert result.always == []
        assert orig_ds == block_ds

    def raises_if_not_a_block() -> None:
        with pytest.raises(LoadError, match="Not a block"):
            ds = _as_ansible({"file": {}})

            loaders.load_block(ds)


def describe_load_play() -> None:
    def loads_correct_play() -> None:
        ds = _as_ansible(
            {
                "hosts": "hello",
                "tasks": [],
            }
        )

        result, orig_ds = loaders.load_play(ds)

        assert result.hosts == ["hello"]
        assert result.tasks == []
        assert ds == orig_ds


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
        ds = _as_ansible({"role": "test"})

        result, parsed_def, orig_ds = loaders.load_role_dependency(ds)

        assert result.role == "test"
        assert result.when == []
        assert parsed_def is None
        assert orig_ds == ds

    def normalises_dependency_with_single_condition() -> None:
        ds = _as_ansible(
            {
                "role": "test",
                "when": "x is True",
            }
        )

        result, parsed_def, orig_ds = loaders.load_role_dependency(ds)

        assert result.role == "test"
        assert result.when == ["x is True"]
        assert parsed_def is None
        assert orig_ds == ds

    def normalises_bare_string_dependency() -> None:
        result, parsed_def, orig_ds = loaders.load_role_dependency("test")

        assert result.role == "test"
        assert result.when == []
        assert parsed_def is None
        assert orig_ds == "test"

    def normalises_dependency_with_name_instead_of_role() -> None:
        ds = _as_ansible({"name": "test"})

        result, parsed_def, orig_ds = loaders.load_role_dependency(ds)

        assert result.role == "test"
        assert result.when == []
        assert parsed_def is None
        assert orig_ds == {"name": "test"}

    def normalises_int_role_name_to_str() -> None:
        result, parsed_def, orig_ds = loaders.load_role_dependency(123)  # type: ignore[arg-type]

        assert result.role == "123"
        assert parsed_def is None
        assert orig_ds == 123

    def raises_on_wrong_dependency_type() -> None:
        with pytest.raises(
            LoadError, match=r"Expected role dependency to be str \| dict"
        ):
            loaders.load_role_dependency(["hello", "world"])  # type: ignore[arg-type]

    def raises_on_missing_dependency_name() -> None:
        with pytest.raises(
            ans.AnsibleError, match="role definitions must contain a role name"
        ):
            ds = _as_ansible({"when": "yes"})

            loaders.load_role_dependency(ds)

    def raises_on_invalid_role_name_type() -> None:
        with pytest.raises(
            ans.AnsibleError, match="role definitions must contain a role name"
        ):
            ds = _as_ansible({"role": ["abc"]})

            loaders.load_role_dependency(ds)

    def considers_extra_non_directive_dependency_properties_to_be_parameters() -> None:
        ds = _as_ansible(
            {
                "role": "test",
                "param_x": 123,
                "become": "yes",
            }
        )

        result, parsed_def, orig_ds = loaders.load_role_dependency(ds)

        assert result.role == "test"
        assert result.become == True
        assert result._role_params == {"param_x": 123}
        assert parsed_def is None
        assert orig_ds == ds

    def loads_new_style_role_requirements() -> None:
        ds = _as_ansible(
            {
                "src": "https://github.com/bennojoy/nginx",
                "version": "main",
            }
        )

        result, parsed_def, orig_ds = loaders.load_role_dependency(
            ds, allow_new_style=True
        )

        assert result.role == "nginx"
        assert parsed_def == {
            "name": "nginx",
            "src": "https://github.com/bennojoy/nginx",
            "version": "main",
            "scm": "git",
        }
        assert orig_ds == ds
