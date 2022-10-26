from pathlib import Path

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

        def should_reject_child_with_different_parent() -> None:
            with pytest.raises(Exception):
                rpp = h.ProjectPath.from_root(Path('meta').absolute())
                rpp.join(Path('tasks/main.yml').absolute())

