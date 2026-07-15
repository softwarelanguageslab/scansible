from __future__ import annotations

from textwrap import dedent

import ansible.parsing.dataloader

from scansible.types import AnyValue


def parse_yaml_dict(yaml_content: str) -> dict[str, AnyValue]:
    """Parse a given YAML string to a dictionary."""
    loader = ansible.parsing.dataloader.DataLoader()
    result = loader.load(data=dedent(yaml_content))
    assert isinstance(result, dict)
    return result


def parse_yaml_list(yaml_content: str) -> list[dict[str, AnyValue]]:
    """Parse a given YAML string to a list of dictionaries."""
    loader = ansible.parsing.dataloader.DataLoader()
    result = loader.load(data=yaml_content)
    assert isinstance(result, list)
    return result
