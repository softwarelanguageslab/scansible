from pathlib import Path

import sys

import pytest

import scansible.representations.structural.helpers as h

def describe_project_path() -> None:

    def describe_ctor() -> None:

        @pytest.mark.parametrize('child_path', [
            'meta/main.yml',
            Path('meta/main.yml'),
            Path('meta/main.yml').absolute()
        ])
        def should_support_various_types_of_child_paths(child_path: str | Path) -> None:
            pp = h.ProjectPath(Path().absolute(), child_path)

            assert pp.root == Path().absolute()
            assert pp.relative == Path('meta/main.yml')
            assert pp.absolute == Path('meta/main.yml').absolute()

        def should_reject_relative_root_paths() -> None:
            with pytest.raises(Exception):
                h.ProjectPath(Path('.'), 'test.yml')

    def describe_from_root() -> None:

        def should_construct_correct_path() -> None:
            pp = h.ProjectPath.from_root(Path().absolute())

            assert pp.root == Path().absolute()
            assert pp.absolute == Path().absolute()
            assert pp.relative == Path('.')

    def describe_join() -> None:

        @pytest.mark.parametrize('child_path', [
            'main.yml',
            Path('main.yml'),
            Path('main.yml').absolute()
        ])
        def should_support_various_types_of_child_paths(child_path: str | Path) -> None:
            rpp = h.ProjectPath.from_root(Path().absolute())
            pp = rpp.join(child_path)

            assert pp.root == rpp.root
            assert pp.relative == Path('main.yml')
            assert pp.absolute == Path('main.yml').absolute()

        def should_remember_root_path() -> None:
            rpp = h.ProjectPath.from_root(Path().absolute())
            pp1 = rpp.join('meta')
            pp2 = pp1.join('main.yml')

            assert pp2.root == rpp.root
            assert pp2.relative == Path('meta/main.yml')

        @pytest.mark.xfail(reason='not implemented any longer')
        def should_reject_child_with_different_parent() -> None:
            with pytest.raises(Exception):
                rpp = h.ProjectPath.from_root(Path('meta').absolute())
                rpp.join(Path('tasks/main.yml').absolute())


def describe_parse_file() -> None:

    @pytest.mark.parametrize('yaml_content,expected', [
        ('hello: world', { 'hello': 'world' }),
        ('- test\n- test2', ['test', 'test2']),
    ])
    def should_parse_valid_yaml(tmp_path: Path, yaml_content: str, expected: object) -> None:
        (tmp_path / 'test.yml').write_text(yaml_content)

        result = h.parse_file(h.ProjectPath(tmp_path, 'test.yml'))

        assert result == expected

    def should_raise_on_invalid_yaml(tmp_path: Path) -> None:
        (tmp_path / 'test.yml').write_text('hello:\n-world')

        with pytest.raises(Exception):
            h.parse_file(h.ProjectPath(tmp_path, 'test.yml'))


def describe_validate_ansible_object() -> None:
    from ansible.playbook.handler import Handler

    def should_normalise_objects() -> None:
        obj = Handler.load({ 'file': {'path': 'x'}, 'listen': 'test' })  # type: ignore[dict-item]
        assert obj.listen == 'test'  # type: ignore[comparison-overlap]

        h.validate_ansible_object(obj)

        assert obj.listen == ['test']

    def should_not_postvalidate_classes() -> None:
        obj = Handler.load({ 'file': {}, 'loop_control': { 'loop_var': 'x' }})  # type: ignore[dict-item]

        h.validate_ansible_object(obj)

        assert obj.loop_control.loop_var == 'x'

    def should_reject_invalid_objects() -> None:
        obj = Handler.load({ 'file': {'path': 'x'}, 'listen': 0 })  # type: ignore[dict-item]

        with pytest.raises(Exception):
            h.validate_ansible_object(obj)

    def does_not_validate_expression_values() -> None:
        obj = Handler.load({ 'file': { 'path': 'x' }, 'become': '{{ test expr }}'})  # type: ignore[dict-item]

        h.validate_ansible_object(obj)

        assert obj.become == '{{ test expr }}'


def describe_find_file() -> None:

    @pytest.mark.parametrize('ext', ['yml', 'yaml', 'json'])
    def should_find_valid_files(tmp_path: Path, ext: str) -> None:
        (tmp_path / f'test.{ext}').touch()

        result = h.find_file(h.ProjectPath.from_root(tmp_path), 'test')

        assert result and result.relative == Path(f'test.{ext}')

    def should_not_find_files_that_dont_exist(tmp_path: Path) -> None:
        result = h.find_file(h.ProjectPath.from_root(tmp_path), 'test')

        assert result is None


def describe_find_all_files() -> None:

    def should_find_all_files(tmp_path: Path) -> None:
        (tmp_path / 'test.yml').touch()
        (tmp_path / 'main.yml').touch()
        rp = h.ProjectPath.from_root(tmp_path)

        result = h.find_all_files(rp)

        assert {child.absolute for child in result} == {rp.absolute / 'test.yml', rp.absolute / 'main.yml'}

    def should_find_files_in_nested_dirs(tmp_path: Path) -> None:
        (tmp_path / 'test.yml').touch()
        (tmp_path / 'tasks').mkdir()
        (tmp_path / 'tasks' / 'main.yml').touch()
        rp = h.ProjectPath.from_root(tmp_path)

        result = h.find_all_files(rp)

        assert {child.absolute for child in result} == {rp.absolute / 'test.yml', rp.absolute / 'tasks' / 'main.yml'}

    def should_ignore_files_with_unknown_extensions(tmp_path: Path) -> None:
        (tmp_path / 'test.txt').touch()
        rp = h.ProjectPath.from_root(tmp_path)

        result = h.find_all_files(rp)

        assert not result


def describe_capture_output() -> None:
    def should_capture_output_to_stdout() -> None:
        with h.capture_output() as out:
            print('hello world')

        assert out.getvalue() == 'hello world\n'

    def should_capture_output_to_stderr() -> None:
        with h.capture_output() as out:
            print('hello world', file=sys.stderr)

        assert out.getvalue() == 'hello world\n'

    def should_capture_output_to_stdout_and_stderr() -> None:
        with h.capture_output() as out:
            print('hello', file=sys.stderr)
            print('world')

        assert out.getvalue() == 'hello\nworld\n'

def describe_prevent_undesired_operations() -> None:

    def raises_when_load_list_of_tasks_is_called_when_active() -> None:
        with h.prevent_undesired_operations():
            with pytest.raises(h.FatalError):
                from ansible.playbook.helpers import load_list_of_tasks
                load_list_of_tasks()  # type: ignore[call-arg]

    def raises_when_templar_template_is_called_when_active() -> None:
        from ansible.template import Templar
        import ansible.parsing.dataloader
        with h.prevent_undesired_operations():
            with pytest.raises(h.FatalError):
                t = Templar(loader=ansible.parsing.dataloader.DataLoader())
                t.template('{{ 1 + 1 }}')

    def raises_when_templar_do_template_is_called_when_active() -> None:
        from ansible.template import Templar
        import ansible.parsing.dataloader
        with h.prevent_undesired_operations():
            with pytest.raises(h.FatalError):
                t = Templar(loader=ansible.parsing.dataloader.DataLoader())
                t.do_template('{{ 1 + 1 }}')

    def allows_calls_when_inactive() -> None:
        from ansible.template import Templar
        import ansible.parsing.dataloader
        with h.prevent_undesired_operations():
            pass

        t = Templar(loader=ansible.parsing.dataloader.DataLoader())
        assert t.template('{{ 1 + 1 }}') == '2'
