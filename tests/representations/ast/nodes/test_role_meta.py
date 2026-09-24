# pyright: reportUnusedFunction = false

from __future__ import annotations

from pathlib import Path
from textwrap import dedent

import pytest
from pydantic import ValidationError

from scansible.ast import ExtractionContext, MetaFile
from scansible.ast.nodes.expression import BoolLiteral, Condition
from scansible.utils import ProjectPath


def describe_extracting_metadata_file():
    def rejects_empty_metadata(tmp_path: Path):
        _ = (tmp_path / "main.yml").write_text("")
        ctx = ExtractionContext(lenient=False)

        with pytest.raises(ValidationError):
            _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

    @pytest.mark.parametrize("content", ["- hello\n- world"])  # list  # string
    def rejects_invalid_files(tmp_path: Path, content: str):
        _ = (tmp_path / "main.yml").write_text(content)
        ctx = ExtractionContext(lenient=False)

        with pytest.raises(ValidationError):
            _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

    def describe_platforms():
        def extracts_standard_platforms_without_dependencies(tmp_path: Path):
            yaml = """
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
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert result.path == Path("main.yml")
            assert len(result.metablock.platforms) == 3
            assert result.metablock.platforms[0].name == "Debian"
            assert result.metablock.platforms[0].version == "any"
            assert result.metablock.platforms[1].name == "Fedora"
            assert result.metablock.platforms[1].version == "7"
            assert result.metablock.platforms[2].name == "Fedora"
            assert result.metablock.platforms[2].version == "8"
            assert not result.metablock.platforms[0].location.is_synthetic
            assert result.metablock.platforms[0].location.start.line == 8
            assert not result.metablock.dependencies

        def normalizes_missing_platforms_property(tmp_path: Path):
            yaml = """
                galaxy_info:
                  name: test
                  author: test
                dependencies: []
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert not result.metablock.platforms

        def rejects_invalid_galaxy_info(tmp_path: Path):
            yaml = """
                galaxy_info:
                    - test
                    - test2
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        def rejects_invalid_platforms_list(tmp_path: Path):
            yaml = """
                galaxy_info:
                    platforms: yes
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        def rejects_weird_platform_entry(tmp_path: Path):
            yaml = """
                galaxy_info:
                    platforms:
                    - [hello]
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        def normalizes_missing_galaxy_info_property(tmp_path: Path):
            yaml = """
                dependencies: []
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert not result.metablock.platforms

        def ignores_malformed_platform_in_lenient_mode(tmp_path: Path):
            yaml = """
                galaxy_info:
                    platforms:
                        - CentOS6
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=True)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert result.metablock.platforms == ()
            assert ctx.broken_tasks[0].raw == "CentOS6"

    def describe_dependencies():
        def extracts_simple_string_dependencies(tmp_path: Path):
            yaml = """
                dependencies:
                    - testrole
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"

        def extracts_simple_dict_dependencies_with_role_key(tmp_path: Path):
            yaml = """
                dependencies:
                    - role: testrole
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"

        def normalizes_int_role_name_to_str(tmp_path: Path):
            yaml = """
                dependencies:
                    - 123
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "123"

        def extracts_simple_dict_dependencies_with_name_key(tmp_path: Path):
            yaml = """
                dependencies:
                    - name: testrole
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].name == "testrole"
            assert result.metablock.dependencies[0].role == "testrole"

        def extracts_dependencies_with_condition(tmp_path: Path):
            yaml = """
                dependencies:
                    - role: testrole
                      when: "ansible_os_family == 'Debian'"
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"
            assert len(result.metablock.dependencies[0].when) == 1
            c = result.metablock.dependencies[0].when[0]
            assert isinstance(c, Condition)
            assert c.raw == "ansible_os_family == 'Debian'"

        def extracts_dependencies_with_multiple_conditions(tmp_path: Path):
            yaml = """
                dependencies:
                    - role: testrole
                      when:
                        - "ansible_os_family == 'Debian'"
                        - "1 + 1 == 2"
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"
            assert len(result.metablock.dependencies[0].when) == 2
            c0, c1 = result.metablock.dependencies[0].when
            assert isinstance(c0, Condition)
            assert c0.raw == "ansible_os_family == 'Debian'"
            assert isinstance(c1, Condition)
            assert c1.raw == "1 + 1 == 2"

        def ignores_malformed_dependency_in_lenient_mode(tmp_path: Path):
            yaml = """
                dependencies:
                    - test: nope
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=True)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert result.metablock.dependencies == ()
            assert ctx.broken_tasks[0].raw == {"test": "nope"}

        def normalizes_missing_dependencies_property(tmp_path: Path):
            yaml = """
                galaxy_info:
                  name: test
                  author: test
                  platforms: []
            """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert not result.metablock.dependencies

        def raises_on_wrong_dependencies_type(tmp_path: Path):
            yaml = """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        test: x
                """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        def raises_on_wrong_dependency_type(tmp_path: Path):
            yaml = """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - [a, b]
                """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        def raises_on_missing_role_name(tmp_path: Path):
            yaml = """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - when: x is True
                """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        def raises_on_invalid_role_name_type(tmp_path: Path):
            yaml = """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - name: [not, a, string]
                """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            with pytest.raises(ValidationError):
                _ = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

        def considers_extra_non_directive_dependency_properties_to_be_parameters(
            tmp_path: Path,
        ):
            yaml = """
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
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "test"
            assert result.metablock.dependencies[0].become == BoolLiteral(True)  # noqa: FBT003
            assert result.metablock.dependencies[0].params == {"param_x": 123}

        def handles_location_argument(tmp_path: Path):
            """`location` as an argument may conflict with our model's attributes."""
            yaml = """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - role: test
                          become: yes
                          param_x: 123
                          location: "start"
                """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "test"
            assert result.metablock.dependencies[0].become == BoolLiteral(True)  # noqa: FBT003
            assert result.metablock.dependencies[0].params == {
                "param_x": 123,
                "location": "start",
            }

        def supports_new_style_role_requirements(tmp_path: Path):
            yaml = """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - src: https://github.com/bennojoy/nginx
                          version: main
                """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "nginx"

        def supports_string_based_new_style_role_requirements(tmp_path: Path):
            yaml = """
                    galaxy_info:
                        platforms:
                            - name: Debian
                              versions:
                                - any

                    dependencies:
                        - git+https://github.com/bennojoy/nginx,main,testrole
                """
            _ = (tmp_path / "main.yml").write_text(dedent(yaml))
            ctx = ExtractionContext(lenient=False)

            result = MetaFile.load(ProjectPath(tmp_path, "main.yml"), ctx)

            assert len(result.metablock.dependencies) == 1
            assert result.metablock.dependencies[0].role == "testrole"
