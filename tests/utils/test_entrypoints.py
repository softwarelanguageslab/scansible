# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import TYPE_CHECKING

import pytest

from scansible.utils.entrypoints import find_entrypoints, is_entrypoint

if TYPE_CHECKING:
    from pathlib import Path

_PLAYBOOK = "- hosts: all\n  tasks: []\n"


# pytest's tmp_path names contain "test", which is_entrypoint ignores, so all
# fixtures live in a differently named subdirectory.
@pytest.fixture
def root(tmp_path: Path) -> Path:
    root = tmp_path / "proj"
    root.mkdir()
    return root


def make_role(path: Path, suffix: str = "yml") -> Path:
    (path / "tasks").mkdir(parents=True)
    _ = (path / "tasks" / f"main.{suffix}").write_text("- debug:\n")
    return path


def make_file(path: Path, content: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    _ = path.write_text(content)
    return path


def describe_is_entrypoint() -> None:
    def describe_name_filters() -> None:
        def should_reject_hidden_files(root: Path) -> None:
            assert not is_entrypoint(make_file(root / ".play.yml", _PLAYBOOK))

        def should_reject_hidden_directories(root: Path) -> None:
            assert not is_entrypoint(make_role(root / ".role"))

        @pytest.mark.parametrize("name", ["test", "MyTests", "molecule", "Molecule"])
        def should_reject_test_and_molecule_directories(root: Path, name: str) -> None:
            assert not is_entrypoint(make_role(root / name))

        def should_reject_test_files(root: Path) -> None:
            assert not is_entrypoint(make_file(root / "test_play.yml", _PLAYBOOK))

    def describe_directories() -> None:
        @pytest.mark.parametrize("suffix", ["yml", "yaml"])
        def should_accept_roles_with_tasks_main(root: Path, suffix: str) -> None:
            assert is_entrypoint(make_role(root / "role", suffix))

        def should_reject_directories_without_tasks_main(root: Path) -> None:
            (root / "plain" / "tasks").mkdir(parents=True)
            assert not is_entrypoint(root / "plain")

    def describe_files() -> None:
        def should_reject_wrong_suffix(root: Path) -> None:
            assert not is_entrypoint(make_file(root / "play.txt", _PLAYBOOK))

        @pytest.mark.parametrize("suffix", ["yml", "yaml", "YML"])
        def should_accept_playbooks(root: Path, suffix: str) -> None:
            assert is_entrypoint(make_file(root / f"play.{suffix}", _PLAYBOOK))

        def should_accept_playbook_imports(root: Path) -> None:
            path = make_file(root / "play.yml", "- import_playbook: other.yml\n")
            assert is_entrypoint(path)

        def should_reject_files_without_hosts_or_import(root: Path) -> None:
            assert not is_entrypoint(make_file(root / "vars.yml", "foo: bar\n"))

        def should_reject_unparseable_yaml(root: Path) -> None:
            path = make_file(root / "broken.yml", "hosts: [unclosed\n")
            assert not is_entrypoint(path)

        def should_reject_top_level_mappings(root: Path) -> None:
            path = make_file(root / "vars.yml", "hosts: all\n")
            assert not is_entrypoint(path)

        def should_reject_sequences_of_non_mappings(root: Path) -> None:
            path = make_file(root / "list.yml", "- hosts\n- all\n")
            assert not is_entrypoint(path)

        def should_reject_plays_without_hosts_or_import(root: Path) -> None:
            path = make_file(root / "list.yml", "- hosts: all\n- name: not a play\n")
            assert not is_entrypoint(path)


def describe_find_entrypoints() -> None:
    def should_find_nothing_in_empty_directory(root: Path) -> None:
        assert find_entrypoints(root) == []

    def should_find_nested_roles(root: Path) -> None:
        role = make_role(root / "a" / "b" / "role")
        assert find_entrypoints(root) == [(role.resolve(), "role")]

    def should_find_nested_playbooks(root: Path) -> None:
        playbook = make_file(root / "a" / "play.yml", _PLAYBOOK)
        assert find_entrypoints(root) == [(playbook.resolve(), "playbook")]

    def should_find_root_itself_if_it_is_an_entrypoint(root: Path) -> None:
        _ = make_role(root)
        assert find_entrypoints(root) == [(root.resolve(), "role")]

    def should_find_roles_and_playbooks_together(root: Path) -> None:
        role = make_role(root / "role")
        playbook = make_file(root / "site.yml", _PLAYBOOK)
        _ = make_file(root / "vars.yml", "foo: bar\n")
        assert sorted(find_entrypoints(root)) == sorted(
            [(role.resolve(), "role"), (playbook.resolve(), "playbook")]
        )

    @pytest.mark.parametrize("name", [".hidden", "tests", "molecule"])
    def should_not_descend_into_skipped_directories(root: Path, name: str) -> None:
        _ = make_file(root / name / "play.yml", _PLAYBOOK)
        _ = make_role(root / name / "role")
        assert find_entrypoints(root) == []

    def should_resolve_symlinked_root(root: Path, tmp_path: Path) -> None:
        _ = make_role(root / "role")
        link = tmp_path / "link"
        link.symlink_to(root, target_is_directory=True)
        assert find_entrypoints(link) == [(root.resolve() / "role", "role")]

    def should_skip_symlinked_children(root: Path, tmp_path: Path) -> None:
        target = make_role(tmp_path / "elsewhere")
        root.joinpath("link").symlink_to(target, target_is_directory=True)
        assert find_entrypoints(root) == []
