# pyright: reportUnusedFunction = false

from __future__ import annotations

import pytest
from _utils import parse_yaml_dict  # pyright: ignore[reportImplicitRelativeImport]
from pydantic import ValidationError

from scansible.representations.structural import ExtractionContext, Handler, Task


def describe_extracting_tasks():
    def extracts_standard_task():
        yaml = """
            name: Ensure file exists
            file:
                path: test.txt
                state: present
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "file"
        assert result.args == {"path": "test.txt", "state": "present"}
        assert result.name == "Ensure file exists"

    def extracts_standard_task_with_action_shorthand():
        yaml = """
            name: Ensure file exists
            file: path=test.txt state=present
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "file"
        assert result.args == {"path": "test.txt", "state": "present"}
        assert result.name == "Ensure file exists"

    def extracts_task_with_vars():
        yaml = """
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            vars:
                file_path: test.txt
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "file"
        assert result.args == {"path": "{{ file_path }}"}
        assert result.name == "Ensure file exists"
        assert result.vars == {"file_path": "test.txt"}

    def extracts_task_with_loop():
        yaml = """
            name: test
            debug: msg={{ item }}
            loop: [hello, world]
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "debug"
        assert result.args == {"msg": "{{ item }}"}
        assert result.name == "test"
        assert result.loop == ["hello", "world"]

    def extracts_task_with_expr_loop():
        yaml = """
            name: test
            debug: msg={{ item }}
            loop: '{{ somelist }}'
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "debug"
        assert result.args == {"msg": "{{ item }}"}
        assert result.name == "test"
        assert result.loop == "{{ somelist }}"

    def extracts_task_with_loop_control():
        yaml = """
            name: test
            debug: msg={{ myvar }}
            loop: [hello, world]
            loop_control:
                loop_var: myvar
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "debug"
        assert result.args == {"msg": "{{ myvar }}"}
        assert result.name == "test"
        assert result.loop == ["hello", "world"]
        assert result.loop_control is not None
        assert result.loop_control.loop_var == "myvar"

    def extracts_task_with_full_loop_control():
        yaml = """
            name: test
            debug: msg={{ myvar }}
            loop: [hello, world]
            loop_control:
                loop_var: myvar
                index_var: myidx
                label: "{{ myvar }}"
                pause: 2
                extended: yes
                extended_allitems: no
                break_when: "{{ myvar == 'world' }}"
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.loop_control is not None
        assert result.loop_control.loop_var == "myvar"
        assert result.loop_control.index_var == "myidx"
        assert result.loop_control.label == "{{ myvar }}"
        assert result.loop_control.pause == 2
        assert result.loop_control.extended is True
        assert result.loop_control.extended_allitems is False
        assert result.loop_control.break_when == ["{{ myvar == 'world' }}"]

    def extracts_task_with_literal_boolean_when():
        yaml = """
            name: test
            debug: msg={{ myvar }}
            when: yes
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "debug"
        assert result.args == {"msg": "{{ myvar }}"}
        assert result.name == "test"
        assert result.when == [True]

    def does_not_eagerly_evaluate_imports():
        yaml = """
            import_tasks: tasks.yml
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "import_tasks"
        assert result.args == {"_raw_params": "tasks.yml"}

    def does_not_eagerly_evaluate_expressions():
        # register is a "static" field and Ansible will try to evaluate the
        # expression eagerly, which we should prevent
        yaml = """
            name: test
            debug:
                msg: hello
            register: '{{ expr }}'
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "debug"
        assert result.args == {"msg": "hello"}
        assert result.name == "test"
        assert result.register_var == "{{ expr }}"

    def does_not_eagerly_resolve_actions():
        yaml = """
            name: test
            action_that_doesnt_exist:
                msg: hello
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "action_that_doesnt_exist"
        assert result.args == {"msg": "hello"}
        assert result.name == "test"

    def extracts_include_role_task():
        yaml = """
            include_role:
                name: testrole
                public: true
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "include_role"
        assert result.args == {"name": "testrole", "public": True}

    def rejects_tasks_with_invalid_attribute_values():
        yaml = """
            name: test
            file:
                path: test.txt
            vars: 0
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_tasks_with_invalid_postvalidated_attribute_values():
        yaml = """
            name: test
            file:
                path: test.txt
            loop_control: 0
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_tasks_with_no_action():
        yaml = """
            name: test
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_tasks_with_multiple_actions():
        yaml = """
            name: test
            file:
                path: test.txt
            apt:
                name: test.txt
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)


def describe_extracting_handlers():
    def extracts_handler_with_listen():
        yaml = """
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            listen: a topic
        """
        ctx = ExtractionContext(False)

        result = Handler.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert result.action == "file"
        assert result.name == "Ensure file exists"
        assert result.args == {"path": "{{ file_path }}"}
        assert result.listen == ["a topic"]

    def extracts_handler_with_list_of_listens():
        yaml = """
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            listen:
                - a topic
                - another topic
        """
        ctx = ExtractionContext(False)

        result = Handler.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result is not None
        assert result.action == "file"
        assert result.name == "Ensure file exists"
        assert result.args == {"path": "{{ file_path }}"}
        assert result.listen == ["a topic", "another topic"]


def describe_parsing_action():

    # Yes, all of these are legal :exploding_head:
    @pytest.mark.parametrize(
        ["task", "expected_action", "expected_args"],
        [
            pytest.param(
                {"debug": {"msg": "hi"}},
                "debug",
                {"msg": "hi"},
                id="module name with args dict",
            ),
            pytest.param(
                {"debug": {"msg": "hi"}, "name": "", "when": ["x"], "vars": {}},
                "debug",
                {"msg": "hi"},
                id="module name with args dict and additional task directives",
            ),
            pytest.param(
                {"debug": "msg=hi"},
                "debug",
                {"msg": "hi"},
                id="module name with k=v args",
            ),
            pytest.param(
                {"shell": "echo hi"},
                "shell",
                {"_raw_params": "echo hi"},
                id="module name with freeform args",
            ),
            pytest.param(
                {"shell": "echo hi", "args": {"chdir": "/tmp"}},
                "shell",
                {"_raw_params": "echo hi", "chdir": "/tmp"},
                id="module name with freeform and structured args",
            ),
            pytest.param(
                {"ping": None},
                "ping",
                {},
                id="module name without args",
            ),
            pytest.param(
                {"action": "debug msg=hi"},
                "debug",
                {"msg": "hi"},
                id="legacy action form with k=v args",
            ),
            pytest.param(
                {"action": "shell echo hi"},
                "shell",
                {"_raw_params": "echo hi"},
                id="legacy action form with freeform args",
            ),
            pytest.param(
                {"action": "ping"},
                "ping",
                {},
                id="legacy action form without args",
            ),
            pytest.param(
                {"action": "debug", "args": {"msg": "hi"}},
                "debug",
                {"msg": "hi"},
                id="legacy action form with top-level structured args",
            ),
            pytest.param(
                {"action": {"module": "debug", "args": {"msg": "hi"}}},
                "debug",
                {"msg": "hi"},
                id="legacy action form with nested dict",
            ),
            pytest.param(
                {"action": {"module": "debug", "msg": "hi"}},
                "debug",
                {"msg": "hi"},
                id="legacy action form with nested dict and flat args",
            ),
        ],
    )
    def extracts_correct_action(
        task: dict[str, object],
        expected_action: str,
        expected_args: dict[str, object],
    ):
        result = Task.model_validate(task)

        assert result.action == expected_action
        assert result.args == expected_args
        assert result.delegate_to is None

    @pytest.mark.parametrize(
        ["task", "expected_action", "expected_args"],
        [
            pytest.param(
                {"local_action": "shell echo hi"},
                "shell",
                {"_raw_params": "echo hi"},
                id="legacy local_action form with freeform args",
            ),
            pytest.param(
                {"local_action": "debug msg=hi"},
                "debug",
                {"msg": "hi"},
                id="legacy local_action form with k=v args",
            ),
        ],
    )
    def extracts_local_action(
        task: dict[str, object], expected_action: str, expected_args: dict[str, object]
    ):
        result = Task.model_validate(task)

        assert result.action == expected_action
        assert result.args == expected_args
        assert result.delegate_to == "localhost"

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
    def rejects_invalid_actions(task: dict[str, object]):
        with pytest.raises(ValidationError):
            _ = Task.model_validate(task)


def describe_normalization():
    def normalizes_none_when():
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        yaml = """
            get_url:
                url: ...
                dest: ...
            when:
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.when == ()

    def extracts_task_with_always_run():
        # devops-cmp/ansible-nodejs/tasks/main.yml @ ce6141fb61f1573b705db7006683af59ea792978
        yaml = """
            get_url:
                url: ...
                dest: ...
            always_run: yes
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.check_mode is False

    @pytest.mark.parametrize("method", ["su", "sudo"])
    def transforms_old_become(method: str):
        yaml = f"""
            file:
            {method}: yes
            {method}_user: me
            {method}_exe: test
            {method}_flags: --flag
            {method}_pass: sekrit
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "file"
        assert result.become is True
        assert result.become_user == "me"
        assert result.become_exe == "test"
        assert result.become_flags == "--flag"
        assert result.vars == {"ansible_become_password": "sekrit"}

    @pytest.mark.parametrize("method", ["su", "sudo"])
    def transforms_old_become_with_multiple_vars(method: str):
        yaml = f"""
            file:
            {method}: yes
            {method}_user: me
            {method}_exe: test
            {method}_flags: --flag
            {method}_pass: sekrit
            vars:
                other: hello
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "file"
        assert result.become is True
        assert result.become_user == "me"
        assert result.become_exe == "test"
        assert result.become_flags == "--flag"
        assert result.vars == {
            "other": "hello",
            "ansible_become_password": "sekrit",
        }

    @pytest.mark.parametrize(
        "combo", [("su", "sudo"), ("sudo", "become"), ("su", "become")]
    )
    def rejects_duplicate_become_method(combo: tuple[str, str]):
        yaml = f"""
            file:
            {combo[0]}: yes
            {combo[1]}: yes
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError, match="Invalid mix of directives"):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def transforms_deprecated_with_keyword():
        yaml = """
            name: test
            file:
                path: '{{ item }}'
            with_items:
                - hello
                - world
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "file"
        assert result.args == {"path": "{{ item }}"}
        assert result.name == "test"
        assert result.loop == ["hello", "world"]
        assert result.loop_with == "items"

    def transforms_include_task():
        yaml = """
            include: test.yml
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "include_tasks"
        assert result.args == {"_raw_params": "test.yml"}

    def transforms_include_static_task():
        yaml = """
            include: test.yml
            static: yes
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "import_tasks"
        assert result.args == {"_raw_params": "test.yml"}

    def transforms_include_nonstatic_task():
        yaml = """
            include: test.yml
            static: no
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.action == "include_tasks"
        assert result.args == {"_raw_params": "test.yml"}


def describe_validation():
    def rejects_import_playbook_action():
        yaml = """
            import_playbook: site.yml
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_include_tasks_marked_static():
        yaml = """
            include_tasks: test.yml
            static: yes
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError, match="include_tasks with static: yes"):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_import_tasks_marked_nonstatic():
        yaml = """
            import_tasks: test.yml
            static: no
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError, match="import_tasks with static: no"):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_duplicate_loop_statements():
        yaml = """
            file:
            loop: [hello, world]
            with_items: [hello, world]
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError, match="duplicate loop statements"):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

    def rejects_unsupported_directive_on_include_tasks():
        yaml = """
            include_tasks: test.yml
            become: yes
        """
        ctx = ExtractionContext(False)

        with pytest.raises(ValidationError, match="Unsupported directives"):
            _ = Task.model_validate(parse_yaml_dict(yaml), context=ctx)


def describe_common_directives():
    def normalizes_single_tag():
        yaml = """
            file: {}
            tags: web
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.tags == ["web"]

    def normalizes_single_collection():
        yaml = """
            file: {}
            collections: community.general
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.collections == ["community.general"]

    def normalizes_single_module_defaults_entry():
        yaml = """
            file: {}
            module_defaults:
                file:
                    mode: "0644"
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.module_defaults == [{"file": {"mode": "0644"}}]

    def normalizes_single_environment_entry():
        yaml = """
            file: {}
            environment:
                PATH: /custom/bin
        """
        ctx = ExtractionContext(False)

        result = Task.model_validate(parse_yaml_dict(yaml), context=ctx)

        assert result.environment == [{"PATH": "/custom/bin"}]
