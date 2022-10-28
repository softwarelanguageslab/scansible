from __future__ import annotations

from typing import Any, Callable

from pathlib import Path

import pytest

from scansible.representations.structural import loaders, ansible_types as ans, helpers as h
from scansible.representations.structural.loaders import LoadError

LoadMetaType = Callable[[str], tuple[dict[str, 'ans.AnsibleValue'], Any]]
LoadVarsType = Callable[[str], tuple[dict[str, 'ans.AnsibleValue'], Any]]
LoadTasksFileType = Callable[[str], tuple[list[dict[str, 'ans.AnsibleValue']], Any]]
LoadPlaybookType = Callable[[str], tuple[list[dict[str, 'ans.AnsibleValue']], Any]]

@pytest.fixture()
def load_meta(tmp_path: Path) -> LoadMetaType:
    def inner(yaml_content: str) -> tuple[dict[str, ans.AnsibleValue], Any]:
        (tmp_path / 'main.yml').write_text(yaml_content)
        return loaders.load_role_metadata(h.ProjectPath(tmp_path, 'main.yml'))
    return inner

@pytest.fixture()
def load_vars(tmp_path: Path) -> LoadVarsType:
    def inner(yaml_content: str) -> tuple[dict[str, ans.AnsibleValue], Any]:
        (tmp_path / 'main.yml').write_text(yaml_content)
        return loaders.load_variable_file(h.ProjectPath(tmp_path, 'main.yml'))
    return inner


@pytest.fixture()
def load_tasks_file(tmp_path: Path) -> LoadTasksFileType:
    def inner(yaml_content: str) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
        (tmp_path / 'main.yml').write_text(yaml_content)
        return loaders.load_tasks_file(h.ProjectPath(tmp_path, 'main.yml'))
    return inner


@pytest.fixture()
def load_pb(tmp_path: Path) -> LoadPlaybookType:
    def inner(yaml_content: str) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
        (tmp_path / 'pb.yml').write_text(yaml_content)
        return loaders.load_playbook(h.ProjectPath(tmp_path, 'pb.yml'))
    return inner


def describe_load_role_metadata() -> None:

    def loads_correct_metadata(load_meta: LoadMetaType) -> None:
        result = load_meta('''
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
        ''')

        assert result[0] == {
            'galaxy_info': {
                'name': 'test',
                'author': 'test',
                'platforms': [{
                    'name': 'Debian',
                    'versions': ['any', 'all']
                }, {
                    'name': 'Fedora',
                    'versions': [9]
                }],
            },
            'dependencies': [{
                'name': 'test',
                'when': ['x is True', 'y is True'],
            }]
        }

    def normalises_missing_galaxy_info_property(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta('''
                dependencies: []
            ''')

            assert isinstance(result[0]['galaxy_info'], dict)
            assert 'galaxy_info' not in result[1]

    def raises_on_empty_metadata(load_meta: LoadMetaType) -> None:
        with pytest.raises(LoadError, match='Empty metadata'):
            load_meta('')

    def raises_on_wrong_metadata_type(load_meta: LoadMetaType) -> None:
        with pytest.raises(LoadError, match='Expected role metadata to be dict'):
            load_meta('- test\n- test2')

    def raises_on_wrong_galaxy_info_type(load_meta: LoadMetaType) -> None:
        with pytest.raises(LoadError, match='Expected role metadata galaxy_info to be dict'):
            load_meta('''
                galaxy_info:
                    - test
                    - test2
            ''')

    def describe_loading_platforms() -> None:
        def normalises_missing_platforms_property(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta('''
                galaxy_info:
                  name: test
                  author: test
                dependencies: []
            ''')

            assert result[0]['galaxy_info']['platforms'] == []
            assert 'platforms' not in result[1]['galaxy_info']

        def raises_on_wrong_platforms_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Expected role metadata galaxy_info.platforms to be list'):
                load_meta('''
                    galaxy_info:
                        platforms: Debian

                    dependencies: []
                ''')

        def raises_on_wrong_platform_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Expected role metadata platform to be dict'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - Debian

                    dependencies: []
                ''')

        def raises_on_missing_platform_name(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Missing property "name"'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - versions: [1, 2]

                    dependencies: []
                ''')

        def raises_on_missing_platform_versions(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Missing property "versions"'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian

                    dependencies: []
                ''')

        def raises_on_superfluous_platform_properties(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Superfluous properties in platform'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - all
                              test: test

                    dependencies: []
                ''')

        def raises_on_wrong_platform_name_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Expected platform name to be str'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: 1
                              versions: [1, 2]

                    dependencies: []
                ''')

        def raises_on_wrong_platform_versions_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match=r'Expected platform versions to be list\[str \| int \| float\]'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions: all

                    dependencies: []
                ''')

        def raises_on_wrong_platform_version_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match=r'Expected platform versions to be list\[str \| int \| float\]'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - x: yes
                                  y: no

                    dependencies: []
                ''')

    def describe_loading_dependencies() -> None:
        def normalises_missing_dependencies_property(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta('''
                galaxy_info:
                  name: test
                  author: test
                  platforms: []
            ''')

            assert result[0]['dependencies'] == []
            assert 'dependencies' not in result[1]

        def normalises_dependency_without_condition(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta('''
                galaxy_info:
                  name: test
                  author: test
                dependencies:
                  - name: test
            ''')

            assert result[0]['dependencies'] == [{'name': 'test', 'when': []}]
            assert 'when' not in result[1]['dependencies'][0]

        def normalises_dependency_with_single_condition(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta('''
                galaxy_info:
                  name: test
                  author: test
                dependencies:
                  - name: test
                    when: x is True
            ''')

            assert result[0]['dependencies'] == [{'name': 'test', 'when': ['x is True']}]
            assert isinstance(result[1]['dependencies'][0]['when'], str)

        def normalises_bare_string_dependency(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta('''
                galaxy_info:
                  name: test
                  author: test
                dependencies:
                  - test
            ''')

            assert result[0]['dependencies'] == [{'name': 'test', 'when': []}]
            assert isinstance(result[1]['dependencies'][0], str)

        def normalises_dependency_with_role_instead_of_name(load_meta: LoadMetaType) -> None:
            result: tuple[Any, Any] = load_meta('''
                galaxy_info:
                  name: test
                  author: test
                dependencies:
                  - role: test
            ''')

            assert result[0]['dependencies'] == [{'name': 'test', 'when': []}]
            assert result[1]['dependencies'][0] == { 'role': 'test' }

        def raises_on_wrong_dependencies_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Expected role dependencies to be list'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        test: x
                ''')

        def raises_on_wrong_dependency_type(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match=r'Expected role dependency to be str \| dict'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        -
                          - hello
                          - world
                ''')

        def raises_on_missing_dependency_name(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Missing dependency name'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - when: yes
                ''')

        def raises_on_wrong_dependency_name(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match=r'Expected dependency name to be str'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - name: 123
                ''')

        def raises_on_multiple_dependency_names(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='"name" and "role" are mutually exclusive'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - name: test
                          role: test
                ''')

        def raises_on_wrong_dependency_when(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match=r'Expected dependency condition to be str \| list\[str\]'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - name: test
                          when:
                            x: 123
                ''')

        def raises_on_superfluous_depedency_properties(load_meta: LoadMetaType) -> None:
            with pytest.raises(LoadError, match='Superfluous properties in dependency'):
                load_meta('''
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - all

                    dependencies:
                        - name: test
                          test: test
                ''')


def describe_load_variable_file() -> None:

    def loads_correct_file(load_vars: LoadVarsType) -> None:
        result = load_vars('''
            test: 123
            hello:
              x:
               - 1
               - b
              y: true
        ''')

        assert result[0] == {
            'test': 123,
            'hello': {
                'x': [1, 'b'],
                'y': True,
            }
        }

    def normalises_empty_file(load_vars: LoadVarsType) -> None:
        result, raw_result = load_vars('# just a comment')

        assert result == {}
        assert raw_result is None

    def raises_on_wrong_type(load_vars: LoadVarsType) -> None:
        with pytest.raises(LoadError, match='Expected variable file to be dict'):
            load_vars('''
                - a
                - b
            ''')

    def raises_on_wrong_name_type(load_vars: LoadVarsType) -> None:
        with pytest.raises(LoadError, match='Expected variable name to be str'):
            load_vars('''
                1: 2
            ''')

def describe_load_task_file() -> None:

    def loads_correct_file(load_tasks_file: LoadTasksFileType) -> None:
        result = load_tasks_file('''
            - name: test
              file: {}
            - block:
                - file: {}
        ''')

        assert result[0] == [{
            'name': 'test',
            'file': {},
        }, {
            'block': [{
                'file': {},
            }]
        }]

    def normalises_empty_file(load_tasks_file: LoadTasksFileType) -> None:
        result, raw_result = load_tasks_file('# just a comment')

        assert result == []
        assert raw_result is None

    def raises_on_wrong_type(load_tasks_file: LoadTasksFileType) -> None:
        with pytest.raises(LoadError, match='Expected task file to be list'):
            load_tasks_file('''
                a: 123
            ''')

    def raises_on_wrong_property_type(load_tasks_file: LoadTasksFileType) -> None:
        with pytest.raises(LoadError, match=r'Expected task file content to be dict\[str, typing\.Any\]'):
            load_tasks_file('''
                - 1: 2
            ''')


def describe_load_task() -> None:

    def loads_correct_task() -> None:
        result = loaders.load_task({  # type: ignore[call-overload]
            'file': {
                'path': 'test.txt',
                'state': 'present',
            },
            'when': 'x is not None'
        }, as_handler=False)

        assert isinstance(result[0], ans.Task)
        assert result[0].action == 'file'
        assert result[0].args == {'path': 'test.txt', 'state': 'present'}
        assert result[0].when == ['x is not None']

    def loads_correct_handler() -> None:
        result = loaders.load_task({  # type: ignore[call-overload]
            'file': {
                'path': 'test.txt',
                'state': 'present',
            },
            'when': 'x is not None',
            'listen': 'test',
        }, as_handler=True)

        assert isinstance(result[0], ans.Handler)
        assert result[0].action == 'file'
        assert result[0].args == {'path': 'test.txt', 'state': 'present'}
        assert result[0].when == ['x is not None']
        assert result[0].listen == ['test']

    def loads_correct_task_include() -> None:
        result = loaders.load_task({  # type: ignore[call-overload]
            'include_tasks': 'test.yml',
            'when': 'x is not None'
        }, as_handler=False)

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == 'include_tasks'
        assert result[0].args == {'_raw_params': 'test.yml'}
        assert result[0].when == ['x is not None']

    def loads_correct_task_include_import() -> None:
        result = loaders.load_task({  # type: ignore[call-overload]
            'import_tasks': 'test.yml',
            'when': 'x is not None'
        }, as_handler=False)

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == 'import_tasks'
        assert result[0].args == {'_raw_params': 'test.yml'}
        assert result[0].when == ['x is not None']

    def loads_correct_handler_include() -> None:
        result = loaders.load_task({  # type: ignore[call-overload]
            'include_tasks': 'test.yml',
            'listen': 'test',
        }, as_handler=True)

        assert isinstance(result[0], ans.HandlerTaskInclude)
        assert result[0].action == 'include_tasks'
        assert result[0].args == {'_raw_params': 'test.yml'}
        assert result[0].listen == ['test']

    def transforms_static_include() -> None:
        result = loaders.load_task({  # type: ignore[call-overload]
            'include': 'test.yml',
            'static': 'yes',
        }, as_handler=False)

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == 'import_tasks'
        assert result[0].args == {'_raw_params': 'test.yml'}
        assert 'include' in result[1]
        assert 'static' in result[1]
        assert 'import_tasks' not in result[1]

    def transforms_static_no_include() -> None:
        result = loaders.load_task({  # type: ignore[call-overload]
            'include': 'test.yml',
            'static': 'no',
        }, as_handler=False)

        assert isinstance(result[0], ans.TaskInclude)
        assert result[0].action == 'include_tasks'
        assert result[0].args == {'_raw_params': 'test.yml'}
        assert 'include' in result[1]
        assert 'static' in result[1]
        assert 'include_tasks' not in result[1]

def describe_load_block() -> None:
    def loads_correct_block() -> None:
        result = loaders.load_block({
            'block': [{'file': {}}],  # type: ignore[dict-item]
            'rescue': [{'file': {}}],  # type: ignore[dict-item]
        })

        assert result[0].block == [{'file': {}}]
        assert result[0].rescue == [{'file': {}}]
        assert result[0].always == []

    def raises_if_not_a_block() -> None:
        with pytest.raises(LoadError, match='Not a block'):
            loaders.load_block({
                'file': {}  # type: ignore[dict-item]
            })


def describe_load_play() -> None:
    def loads_correct_play() -> None:
        result = loaders.load_play({
            'hosts': 'hello',  # type: ignore[dict-item]
            'tasks': [],  # type: ignore[dict-item]
        })

        assert result[0].hosts == ['hello']
        assert result[0].tasks == []


def describe_load_playbook() -> None:
    def loads_correct_playbook(load_pb: LoadPlaybookType) -> None:
        result = load_pb('''---
            - hosts: servers
              name: x
              tasks: []
            - hosts: databases
              name: x
              tasks: []
        ''')

        assert result[0] == [{
            'hosts': 'servers',
            'name': 'x',
            'tasks': [],
        }, {
            'hosts': 'databases',
            'name': 'x',
            'tasks': [],
        }]

    def raises_on_empty_playbook(load_pb: LoadPlaybookType) -> None:
        with pytest.raises(LoadError, match='Empty playbook'):
            load_pb('# just a comment')

    def raises_on_wrong_type(load_pb: LoadPlaybookType) -> None:
        with pytest.raises(LoadError, match='Expected playbook to be list'):
            load_pb('''
                hosts: x
                name: test
            ''')
