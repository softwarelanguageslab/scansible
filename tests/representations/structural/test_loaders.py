from __future__ import annotations

from typing import Any, Callable

from pathlib import Path

import pytest

from scansible.representations.structural import loaders, ansible_types as ans, helpers as h
from scansible.representations.structural.loaders import LoadError

LoadMetaType = Callable[[str], tuple[dict[str, 'ans.AnsibleValue'], Any]]

def describe_load_role_metadata() -> None:

    @pytest.fixture()
    def load_meta(tmp_path: Path) -> LoadMetaType:
        def inner(yaml_content: str) -> tuple[dict[str, ans.AnsibleValue], Any]:
            (tmp_path / 'main.yml').write_text(yaml_content)
            return loaders.load_role_metadata(h.ProjectPath(tmp_path, 'main.yml'))
        return inner

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
