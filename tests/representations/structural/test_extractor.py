from __future__ import annotations

from typing import Any, Callable, Type

from pathlib import Path
from textwrap import dedent

import ansible.parsing.dataloader
import pytest
from pytest_describe import behaves_like

from scansible.representations.structural import extractor as ext, representation as rep, ansible_types as ans

def _parse_yaml(yaml_content: str) -> Any:
    loader = ansible.parsing.dataloader.DataLoader()
    return loader.load(yaml_content)

def describe_extracting_metadata_file() -> None:

    def extracts_standard_metadata_without_dependencies(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
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
        '''))

        result = ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.metablock.parent is result
        assert result == rep.MetaFile(
            Path('main.yml'),
            rep.MetaBlock(
                platforms=[
                    rep.Platform(name='Debian', version='any'),
                    rep.Platform(name='Fedora', version=7),
                    rep.Platform(name='Fedora', version=8),
                ],
                raw=None))

    def extracts_simple_string_dependencies(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent(f'''
            dependencies:
                - testrole
        '''))

        result = ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.metablock.dependencies == [rep.Dependency(role='testrole')]

    @pytest.mark.parametrize('key', ['name', 'role'])
    def extracts_simple_dict_dependencies(tmp_path: Path, key: str) -> None:
        (tmp_path / 'main.yml').write_text(dedent(f'''
            dependencies:
                - {key}: testrole
        '''))

        result = ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.metablock.dependencies == [rep.Dependency(role='testrole')]

    def extracts_dependencies_with_condition(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            dependencies:
                - role: testrole
                  when: "{{ ansible_os_family == 'Debian' }}"
        '''))

        result = ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.metablock.dependencies == [rep.Dependency(role='testrole', when=["{{ ansible_os_family == 'Debian' }}"])]

    def extracts_dependencies_with_multiple_conditions(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            dependencies:
                - role: testrole
                  when:
                    - "{{ ansible_os_family == 'Debian' }}"
                    - "{{ 1 + 1 == 2 }}"
        '''))

        result = ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.metablock.dependencies == [rep.Dependency(
            role='testrole',
            when=["{{ ansible_os_family == 'Debian' }}", '{{ 1 + 1 == 2 }}'])]

    def rejects_empty_metadata(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text('')

        with pytest.raises(Exception):
            ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))


    @pytest.mark.parametrize('content', [
        '- hello\n- world'  # list
        'test'  # string
    ])
    def rejects_invalid_files(tmp_path: Path, content: str) -> None:
        (tmp_path / 'main.yml').write_text(content)

        with pytest.raises(Exception):
            ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))


    def rejects_invalid_galaxy_info(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            galaxy_info: []
        '''))

        with pytest.raises(Exception):
            ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))

    def rejects_invalid_platforms_list(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            galaxy_info:
                platforms: yes
        '''))

        with pytest.raises(Exception):
            ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))

    def rejects_invalid_platform_entry(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            galaxy_info:
                platforms:
                  - name: [hello]
        '''))

        with pytest.raises(Exception):
            ext.extract_role_metadata_file(ext.ProjectPath(tmp_path, 'main.yml'))


def describe_extracting_variables() -> None:

    def extracts_simple_variables(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            test: hello world
            test2: 123
            test3:
                - hello
                - world
            test4:
                this: is
                a: dict
        '''))

        result = ext.extract_variable_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.file_path == Path('main.yml')
        assert all(v.parent is result for v in result.variables)
        assert sorted(result.variables, key=lambda v: v.name) == [
            rep.Variable('test', 'hello world'),
            rep.Variable('test2', 123),
            rep.Variable('test3', ['hello', 'world']),
            rep.Variable('test4', { 'this': 'is', 'a': 'dict' })
        ]

    def extracts_vault_variables(tmp_path: Path) -> None:
        # ioannis1/pg_config/defaults/main.yml
        (tmp_path / 'main.yml').write_text(dedent('''
            postgres_passwd:     !vault |
                $ANSIBLE_VAULT;1.1;AES256
                62396263313762316136336334303463366465303638626438616530343935623766626534366436
        '''))

        result = ext.extract_variable_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.file_path == Path('main.yml')
        assert all(v.parent is result for v in result.variables)
        assert result.variables == [rep.Variable('postgres_passwd', rep.VaultValue(b'$ANSIBLE_VAULT;1.1;AES256\n62396263313762316136336334303463366465303638626438616530343935623766626534366436\n'))]

    def allows_variable_values_to_be_none(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            test:
        '''))

        result = ext.extract_variable_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.variables == [rep.Variable('test', None)]

    def allows_variable_files_to_be_empty(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            # just a comment
        '''))

        result = ext.extract_variable_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result.variables == []

    @pytest.mark.parametrize('content', [
        '- hello\n- world'  # list
        'test'  # string
    ])
    def rejects_invalid_files(tmp_path: Path, content: str) -> None:
        (tmp_path / 'main.yml').write_text(content)

        with pytest.raises(Exception):
            ext.extract_variable_file(ext.ProjectPath(tmp_path, 'main.yml'))

TaskExtractor = Callable[[dict[str, 'ans.AnsibleValue']], rep.Task]

# Shared behaviour for task extractors
def a_task_extractor() -> None:

    def extracts_standard_task(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: Ensure file exists
            file:
                path: test.txt
                state: present
        ''')))

        assert result == task_representation(
            action='file',
            args={
                'path': 'test.txt',
                'state': 'present',
            },
            name='Ensure file exists',
            raw=None)

    def extracts_standard_task_with_action_shorthand(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: Ensure file exists
            file: path=test.txt state=present
        ''')))

        assert result == task_representation(
            action='file',
            args={
                'path': 'test.txt',
                'state': 'present',
            },
            name='Ensure file exists',
            raw=None)

    def extracts_task_with_vars(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            vars:
                file_path: test.txt
        ''')))

        assert result == task_representation(
            action='file',
            args={
                'path': '{{ file_path }}',
            },
            name='Ensure file exists',
            vars=[rep.Variable('file_path', 'test.txt')],
            raw=None)

    def extracts_task_with_loop(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: test
            debug: msg={{ item }}
            loop: [hello, world]
        ''')))

        assert result == task_representation(
            action='debug',
            args={
                'msg': '{{ item }}',
            },
            name='test',
            loop=['hello', 'world'],
            raw=None)

    def extracts_task_with_expr_loop(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: test
            debug: msg={{ item }}
            loop: '{{ somelist }}'
        ''')))

        assert result == task_representation(
            action='debug',
            args={
                'msg': '{{ item }}',
            },
            name='test',
            loop='{{ somelist }}',
            raw=None)

    def extracts_task_with_loop_control(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: test
            debug: msg={{ myvar }}
            loop: [hello, world]
            loop_control:
              loop_var: myvar
        ''')))

        assert result == task_representation(
            action='debug',
            args={
                'msg': '{{ myvar }}',
            },
            name='test',
            loop=['hello', 'world'],
            loop_control=rep.LoopControl(loop_var='myvar'),
            raw=None)

    def extracts_task_with_literal_boolean_when(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: test
            debug: msg={{ myvar }}
            when: yes
        ''')))

        assert result == task_representation(
            action='debug',
            args={
                'msg': '{{ myvar }}',
            },
            name='test',
            when=[True],
            raw=None)

    def does_not_eagerly_evaluate_imports(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            import_tasks: tasks.yml
        ''')))

        assert result == task_representation(
            action='import_tasks',
            args={
                '_raw_params': 'tasks.yml',
            },
            raw=None)

    def does_not_eagerly_evaluate_expressions(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        # register is a "static" field and Ansible will try to evaluate the
        # expression eagerly, which we should prevent
        result = extractor(_parse_yaml(dedent('''
            name: test
            debug:
                msg: hello
            register: '{{ expr }}'
        ''')))

        assert result == task_representation(
            action='debug',
            args={
                'msg': 'hello',
            },
            name='test',
            register='{{ expr }}',
            raw=None)

    def does_not_eagerly_resolve_actions(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: test
            action_that_doesnt_exist:
                msg: hello
        ''')))

        assert result == task_representation(
            action='action_that_doesnt_exist',
            args={
                'msg': 'hello',
            },
            name='test',
            raw=None)

    def normalises_deprecated_with_keyword(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            name: test
            file:
              path: '{{ item }}'
            with_items:
              - hello
              - world
        ''')))

        assert result == task_representation(
            action='file',
            args={
                'path': '{{ item }}',
            },
            name='test',
            loop=['hello', 'world'],
            loop_with='items',
            raw=None)

    def extracts_include_task(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            include: test.yml
        ''')))

        assert result == task_representation(
            action='include',
            args={
                '_raw_params': 'test.yml',
            },
            raw=None)

    def extracts_include_static_task(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            include: test.yml
            static: yes
        ''')))

        assert result == task_representation(
            action='import_tasks',
            args={
                '_raw_params': 'test.yml',
            },
            raw=None)

    def extracts_include_nonstatic_task(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        result = extractor(_parse_yaml(dedent('''
            include: test.yml
            static: no
        ''')))

        assert result == task_representation(
            action='include_tasks',
            args={
                '_raw_params': 'test.yml',
            },
            raw=None)

    def rejects_tasks_with_invalid_attribute_values(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        with pytest.raises(Exception):
            extractor(_parse_yaml(dedent('''
                name: test
                file:
                    path: test.txt
                vars: 0
            ''')))

    def rejects_tasks_with_invalid_postvalidated_attribute_values(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        with pytest.raises(Exception):
            extractor(_parse_yaml(dedent('''
                name: test
                file:
                    path: test.txt
                loop: 0
            ''')))

    def rejects_tasks_with_no_action(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        with pytest.raises(Exception):
            extractor(_parse_yaml(dedent('''
                name: test
            ''')))

    def rejects_tasks_with_multiple_actions(extractor: TaskExtractor, task_representation: Type[rep.Task]) -> None:
        with pytest.raises(Exception):
            extractor(_parse_yaml(dedent('''
                name: test
                file:
                    path: test.txt
                apt:
                    name: test.txt
            ''')))


@behaves_like(a_task_extractor)
def describe_extracting_tasks() -> None:

    @pytest.fixture()
    def extractor() -> Callable[[dict[str, ans.AnsibleValue]], rep.Task]:
        return ext.extract_task

    @pytest.fixture()
    def task_representation() -> Type[rep.Task]:
        return rep.Task


@behaves_like(a_task_extractor)
def describe_extracting_handlers() -> None:

    @pytest.fixture()
    def extractor() -> Callable[[dict[str, ans.AnsibleValue]], rep.Handler]:
        return ext.extract_handler

    @pytest.fixture()
    def task_representation() -> Type[rep.Handler]:
        return rep.Handler


    def extracts_handler_with_listen() -> None:
        result = ext.extract_handler(_parse_yaml(dedent('''
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            listen: a topic
        ''')))

        assert result == rep.Handler(
            action='file',
            name='Ensure file exists',
            args={'path': '{{ file_path }}'},
            listen=['a topic'],
            raw=None)

    def extracts_handler_with_list_of_listens() -> None:
        result = ext.extract_handler(_parse_yaml(dedent('''
            name: Ensure file exists
            file:
                path: '{{ file_path }}'
            listen:
              - a topic
              - another topic
        ''')))

        assert result == rep.Handler(
            action='file',
            name='Ensure file exists',
            args={'path': '{{ file_path }}'},
            listen=['a topic', 'another topic'],
            raw=None)


def describe_extracting_list_of_handlers() -> None:

    def extracts_as_handlers() -> None:
        result = ext.extract_list_of_tasks_or_blocks(_parse_yaml(dedent('''
            - file: {}
            - apt: {}
        ''')), handlers=True)

        assert len(result) == 2
        assert isinstance(result[0], rep.Handler)
        assert isinstance(result[1], rep.Handler)


def describe_extracting_blocks() -> None:

    def extracts_standard_blocks() -> None:
        result = ext.extract_block(_parse_yaml(dedent('''
            block:
              - name: test
                file: {}
              - name: test2
                file: {}
        ''')))

        assert result == rep.Block(
            block=[  # type: ignore[arg-type]
                rep.Task(action='file', name='test', args={}, raw=None),
                rep.Task(action='file', name='test2', args={}, raw=None),
            ],
            raw=None)
        assert all(child.parent is result for child in result.block + result.rescue + result.always)

    def extracts_block_of_handlers() -> None:
        result = ext.extract_block(_parse_yaml(dedent('''
            block:
              - name: test
                file: {}
              - name: test2
                file: {}
        ''')), handlers=True)

        assert result == rep.Block(
            block=[  # type: ignore[arg-type]
                rep.Handler(action='file', name='test', args={}, raw=None),
                rep.Handler(action='file', name='test2', args={}, raw=None),
            ],
            raw=None)
        assert all(child.parent is result for child in result.block + result.rescue + result.always)

    def extracts_blocks_with_rescue_and_always() -> None:
        result = ext.extract_block(_parse_yaml(dedent('''
            block:
              - name: test
                file: {}
            rescue:
              - name: test2
                file: {}
            always:
              - name: test3
                file: {}
        ''')))

        assert result == rep.Block(
            block=[  # type: ignore[arg-type]
                rep.Task(action='file', name='test', args={}, raw=None),
            ],
            rescue=[  # type: ignore[arg-type]
                rep.Task(action='file', name='test2', args={}, raw=None),
            ],
            always=[  # type: ignore[arg-type]
                rep.Task(action='file', name='test3', args={}, raw=None),
            ],
            raw=None)
        assert all(child.parent is result for child in result.block + result.rescue + result.always)

    def extracts_nested_blocks() -> None:
        result = ext.extract_block(_parse_yaml(dedent('''
            block:
              - name: test
                file: {}
              - block:
                  - name: test
                    file: {}
        ''')))

        assert result == rep.Block(
            block=[  # type: ignore[arg-type]
                rep.Task(action='file', name='test', args={}, raw=None),
                rep.Block(block=[  # type: ignore[arg-type]
                    rep.Task(action='file', name='test', args={}, raw=None),
                ], raw=None),
            ],
            raw=None)
        assert all(child.parent is result for child in result.block + result.rescue + result.always)
        assert isinstance(result.block[1], rep.Block)
        assert all(child.parent is result.block[1] for child in result.block[1].block + result.block[1].rescue + result.block[1].always)

    def does_not_eagerly_load_import_tasks() -> None:
        result = ext.extract_block(_parse_yaml(dedent('''
            block:
              - import_tasks: test
        ''')))

        assert result == rep.Block(
            block=[  # type: ignore[arg-type]
                rep.Task(action='import_tasks', args={'_raw_params': 'test'}, raw=None),
            ],
            raw=None)
        assert all(child.parent is result for child in result.block + result.rescue + result.always)

    def rejects_non_blocks() -> None:
        with pytest.raises(Exception):
            ext.extract_block(_parse_yaml(dedent('''
                import_tasks: test
            ''')))

    def rejects_blocks_without_block() -> None:
        with pytest.raises(Exception):
            ext.extract_block(_parse_yaml(dedent('''
                rescue:
                  - file: {}
            ''')))

def describe_extracting_tasks_file() -> None:
    def extracts_standard_task_files(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text(dedent('''
            - name: hello world
              file:
                path: hello
            - block:
                - name: test
                  test: {}
        '''))

        result = ext.extract_tasks_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result == rep.TaskFile(
            file_path=Path('main.yml'),
            tasks=[  # type: ignore[arg-type]
                rep.Task(
                    action='file',
                    args={'path': 'hello'},
                    name='hello world',
                    raw=None),
                rep.Block(
                    block=[  # type: ignore[arg-type]
                        rep.Task(
                            action='test',
                            args={},
                            name='test',
                            raw=None)
                    ], raw=None)
            ])
        assert all(v.parent is result for v in result.tasks)

    def allows_task_files_to_be_empty(tmp_path: Path) -> None:
        (tmp_path / 'main.yml').write_text('# just a comment')

        result = ext.extract_tasks_file(ext.ProjectPath(tmp_path, 'main.yml'))

        assert result == rep.TaskFile(file_path=Path('main.yml'), tasks=[])

    @pytest.mark.parametrize('content', [
        'hello: world'  # dict
        'test'  # string
    ])
    def rejects_invalid_files(tmp_path: Path, content: str) -> None:
        (tmp_path / 'main.yml').write_text(content)

        with pytest.raises(Exception):
            ext.extract_tasks_file(ext.ProjectPath(tmp_path, 'main.yml'))

def describe_extracting_plays() -> None:

    def extracts_simple_play() -> None:
        result = ext.extract_play(_parse_yaml(dedent('''
            name: test play
            hosts: servers
            tasks:
              - import_tasks: test
        ''')))

        assert result == rep.Play(
            hosts=['servers'],
            name='test play',
            tasks=[
                rep.Task(action='import_tasks', args={'_raw_params': 'test'}, raw=None),
            ],
            raw=None)
        assert all(child.parent is result for child in result.tasks)

    def extracts_play_with_block() -> None:
        result = ext.extract_play(_parse_yaml(dedent('''
            name: test play
            hosts: servers
            tasks:
              - block:
                - import_tasks: test
        ''')))

        assert result == rep.Play(
            hosts=['servers'],
            name='test play',
            tasks=[
                rep.Block(
                    block=[  # type: ignore[arg-type]
                        rep.Task(action='import_tasks', args={'_raw_params': 'test'}, raw=None),
                    ], raw=None)
            ],
            raw=None)
        assert all(child.parent is result for child in result.tasks)

    def extracts_play_with_vars() -> None:
        result = ext.extract_play(_parse_yaml(dedent('''
            name: test play
            hosts: servers
            tasks:
              - import_tasks: test
            vars:
              testvar: 123
        ''')))

        assert result == rep.Play(
            hosts=['servers'],
            name='test play',
            tasks=[
                rep.Task(action='import_tasks', args={'_raw_params': 'test'}, raw=None),
            ],
            vars=[rep.Variable('testvar', 123)],
            raw=None)
        assert all(child.parent is result for child in result.tasks)

    def rejects_invalid_play() -> None:
        with pytest.raises(Exception):
            # missing hosts
            ext.extract_play(_parse_yaml(dedent('''
                name: test play
                tasks:
                  - import_tasks: hello
            ''')))

def describe_extract_playbook() -> None:

    def extracts_correct_playbook(tmp_path: Path) -> None:
        pb_content = dedent('''
            ---
            - hosts: servers
              name: config servers
              tasks:
                - file:
                    path: test.txt
                    state: present
              vars:
                x: 111
        ''')
        raw_pb = _parse_yaml(pb_content)
        (tmp_path / 'pb.yml').write_text(pb_content)
        raw_play = raw_pb[0]
        raw_task = raw_play['tasks'][0]

        result = ext.extract_playbook(tmp_path / 'pb.yml', id='test', version='test2')

        assert result.is_playbook
        assert not result.is_role
        assert isinstance(result.root, rep.Playbook)
        assert all(play.parent is result.root for play in result.root.plays)
        assert result == rep.StructuralModel(
            root=rep.Playbook(
                plays=[
                    rep.Play(
                        hosts=['servers'],
                        name='config servers',
                        tasks=[
                            rep.Task(
                                action='file',
                                args={'path': 'test.txt', 'state': 'present'},
                                raw=raw_task,
                            )
                        ],
                        vars=[rep.Variable('x', 111)],
                        raw=raw_play),
                ],
                raw=raw_pb),
            path=tmp_path / 'pb.yml',
            id='test',
            version='test2',
            logs='',
        )

    def extracts_playbooks_with_multiple_plays(tmp_path: Path) -> None:
        pb_content = dedent('''
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
        ''')
        raw_pb = _parse_yaml(pb_content)
        (tmp_path / 'pb.yml').write_text(pb_content)
        raw_play_1 = raw_pb[0]
        raw_play_2 = raw_pb[1]
        raw_task = raw_play_1['tasks'][0]

        result = ext.extract_playbook(tmp_path / 'pb.yml', id='test', version='test2')

        assert result.is_playbook
        assert not result.is_role
        assert isinstance(result.root, rep.Playbook)
        assert all(play.parent is result.root for play in result.root.plays)
        assert result == rep.StructuralModel(
            root=rep.Playbook(
                plays=[
                    rep.Play(
                        hosts=['servers'],
                        name='config servers',
                        tasks=[
                            rep.Task(
                                action='file',
                                args={'path': 'test.txt', 'state': 'present'},
                                raw=raw_task,
                            )
                        ],
                        vars=[rep.Variable('x', 111)],
                        raw=raw_play_1),
                    rep.Play(
                        hosts=['databases'],
                        name='config databases',
                        raw=raw_play_2),
                ],
                raw=raw_pb),
            path=tmp_path / 'pb.yml',
            id='test',
            version='test2',
            logs='',
        )

    def rejects_empty_playbooks(tmp_path: Path) -> None:
        (tmp_path / 'pb.yml').write_text('')

        with pytest.raises(Exception):
            ext.extract_playbook(tmp_path / 'pb.yml', 'test', 'test2')

def describe_extracting_roles() -> None:

    def extracts_correct_roles(tmp_path: Path) -> None:
        for dirname in ('meta', 'tasks', 'vars', 'defaults', 'handlers'):
            (tmp_path / dirname).mkdir()
        (tmp_path / 'meta' / 'main.yml').write_text(dedent('''
            dependencies: []
            galaxy_info:
              name: test
              author: test
              platforms:
                - name: Debian
                  versions:
                    - all
        '''))
        (tmp_path / 'tasks' / 'main.yml').write_text(dedent('''
            - file:
                path: hello
            - apt:
                name: test
        '''))
        (tmp_path / 'defaults' / 'main.yml').write_text(dedent('''
            a: 123
        '''))
        (tmp_path / 'vars' / 'main.yml').write_text(dedent('''
            b: 456
        '''))
        (tmp_path / 'handlers' / 'main.yml').write_text(dedent('''
            - name: restart x
              service:
                name: test
        '''))

        result = ext.extract_role(tmp_path, 'test', 'test2')

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, rep.Role)
        task_file = rep.TaskFile(
            file_path=Path('tasks/main.yml'),
            tasks=[  # type: ignore[arg-type]
                rep.Task(
                    action='file',
                    args={'path': 'hello'},
                    raw={'file': {'path': 'hello'}},
                ),
                rep.Task(
                    action='apt',
                    args={'name': 'test'},
                    raw={'apt': {'name': 'test'}},
                )])
        meta_file = rep.MetaFile(
            file_path=Path('meta/main.yml'),
            metablock=rep.MetaBlock(
                platforms=[rep.Platform('Debian', 'all')],
                raw={'dependencies': [], 'galaxy_info': {'name': 'test', 'author': 'test', 'platforms': [{'name': 'Debian', 'versions': ['all']}]}}))
        vars_file = rep.VariableFile(
            file_path=Path('vars/main.yml'),
            variables=[rep.Variable('b', 456)])
        defaults_file = rep.VariableFile(
            file_path=Path('defaults/main.yml'),
            variables=[rep.Variable('a', 123)])
        handler_file = rep.TaskFile(
            file_path=Path('handlers/main.yml'),
            tasks=[  # type: ignore[arg-type]
                rep.Handler(
                    name='restart x',
                    action='service',
                    args={'name': 'test'},
                    raw={'name': 'restart x', 'service': {'name': 'test'}},
                )])
        assert result == rep.StructuralModel(
            root=rep.Role(
                meta_file=meta_file,
                task_files={'main.yml': task_file},
                default_var_files={'main.yml': defaults_file},
                role_var_files={'main.yml': vars_file},
                handler_files={'main.yml': handler_file},
                broken_files=[]),
            path=tmp_path,
            id='test',
            version='test2',
            logs='',
        )
        assert result.root.main_tasks_file == task_file
        assert result.root.main_defaults_file == defaults_file
        assert result.root.main_vars_file == vars_file
        assert result.root.main_handlers_file == handler_file

    def extracts_roles_with_files_missing(tmp_path: Path) -> None:
        for dirname in ('meta', 'tasks', 'vars', 'defaults', 'handlers'):
            (tmp_path / dirname).mkdir()
        (tmp_path / 'tasks' / 'main.yml').write_text(dedent('''
            - file:
                path: hello
            - apt:
                name: test
        '''))
        (tmp_path / 'defaults' / 'main.yml').write_text(dedent('''
            a: 123
        '''))

        result = ext.extract_role(tmp_path, 'test', 'test2')

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, rep.Role)
        task_file = rep.TaskFile(
            file_path=Path('tasks/main.yml'),
            tasks=[  # type: ignore[arg-type]
                rep.Task(
                    action='file',
                    args={'path': 'hello'},
                    raw={'file': {'path': 'hello'}},
                ),
                rep.Task(
                    action='apt',
                    args={'name': 'test'},
                    raw={'apt': {'name': 'test'}},
                )])
        defaults_file = rep.VariableFile(
            file_path=Path('defaults/main.yml'),
            variables=[rep.Variable('a', 123)])
        assert result == rep.StructuralModel(
            root=rep.Role(
                meta_file=None,
                task_files={'main.yml': task_file},
                default_var_files={'main.yml': defaults_file},
                role_var_files={},
                handler_files={},
                broken_files=[]),
            path=tmp_path,
            id='test',
            version='test2',
            logs='',
        )
        assert result.root.main_tasks_file == task_file
        assert result.root.main_defaults_file == defaults_file
        assert result.root.main_vars_file is None
        assert result.root.main_handlers_file is None

    def extracts_roles_with_broken_files(tmp_path: Path) -> None:
        for dirname in ('meta', 'tasks', 'vars', 'defaults', 'handlers'):
            (tmp_path / dirname).mkdir()
        (tmp_path / 'tasks' / 'main.yml').write_text(dedent('''
            file:
                path: hello
            apt:
                name: test
        '''))
        (tmp_path / 'defaults' / 'main.yml').write_text(dedent('''
            a: 123
        '''))

        result = ext.extract_role(tmp_path, 'test', 'test2')

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, rep.Role)
        defaults_file = rep.VariableFile(
            file_path=Path('defaults/main.yml'),
            variables=[rep.Variable('a', 123)])
        assert result == rep.StructuralModel(
            root=rep.Role(
                meta_file=None,
                task_files={},
                default_var_files={'main.yml': defaults_file},
                role_var_files={},
                handler_files={},
                broken_files=[rep.BrokenFile(Path('tasks/main.yml'), "Failed to load task file at tasks/main.yml: Wrong type encountered\n\nExpected task file to be list, got AnsibleMapping instead.\nActual value:\n{'file': {'path': 'hello'}, 'apt': {'name': 'test'}}")]),
            path=tmp_path,
            id='test',
            version='test2',
            logs='',
        )
        assert result.root.main_tasks_file == None
        assert result.root.main_defaults_file == defaults_file
        assert result.root.main_vars_file is None
        assert result.root.main_handlers_file is None

    def extracts_roles_with_non_main_files(tmp_path: Path) -> None:
        for dirname in ('meta', 'tasks', 'vars', 'defaults', 'handlers'):
            (tmp_path / dirname).mkdir()
        (tmp_path / 'tasks' / 'main.yml').write_text(dedent('''
            - file:
                path: hello
            - import_tasks: other.yml
        '''))
        (tmp_path / 'tasks' / 'other.yml').write_text(dedent('''
            - apt:
                name: test
        '''))

        (tmp_path / 'defaults' / 'main.yml').write_text(dedent('''
            a: 123
        '''))

        result = ext.extract_role(tmp_path, 'test', 'test2', extract_all=True)

        assert result.is_role
        assert not result.is_playbook
        assert isinstance(result.root, rep.Role)
        defaults_file = rep.VariableFile(
            file_path=Path('defaults/main.yml'),
            variables=[rep.Variable('a', 123)])
        task_file = rep.TaskFile(
            file_path=Path('tasks/main.yml'),
            tasks=[  # type: ignore[arg-type]
                rep.Task(
                    action='file',
                    args={'path': 'hello'},
                    raw={'file': {'path': 'hello'}},
                ),
                rep.Task(
                    action='import_tasks',
                    args={'_raw_params': 'other.yml'},
                    raw={'import_tasks': 'other.yml'},
                )])
        other_task_file = rep.TaskFile(
            file_path=Path('tasks/other.yml'),
            tasks=[  # type: ignore[arg-type]
                rep.Task(
                    action='apt',
                    args={'name': 'test'},
                    raw={'apt': {'name': 'test'}},
                )])
        assert result == rep.StructuralModel(
            root=rep.Role(
                meta_file=None,
                task_files={'main.yml': task_file, 'other.yml': other_task_file},
                default_var_files={'main.yml': defaults_file},
                role_var_files={},
                handler_files={},
                broken_files=[]),
            path=tmp_path,
            id='test',
            version='test2',
            logs='',
        )
        assert result.root.main_tasks_file == task_file
        assert result.root.main_defaults_file == defaults_file
        assert result.root.main_vars_file is None
        assert result.root.main_handlers_file is None
