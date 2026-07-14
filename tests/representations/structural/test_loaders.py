# pyright: reportUnusedFunction = false

from __future__ import annotations

from typing import Any

from collections.abc import Callable
from pathlib import Path

import pytest

from scansible.representations.structural import ansible_types as ans
from scansible.representations.structural import helpers as h
from scansible.representations.structural import loaders
from scansible.representations.structural.loaders import LoadError

LoadPlaybookType = Callable[[str], tuple[list[dict[str, "ans.AnsibleValue"]], Any]]


@pytest.fixture()
def load_pb(tmp_path: Path) -> LoadPlaybookType:
    def inner(yaml_content: str) -> tuple[list[dict[str, ans.AnsibleValue]], Any]:
        (tmp_path / "pb.yml").write_text(yaml_content)
        return loaders.load_playbook(h.ProjectPath(tmp_path, "pb.yml"))

    return inner


# shorthand for cast
def _as_ansible(obj: dict[str, Any]) -> dict[str, ans.AnsibleValue]:
    return obj


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
