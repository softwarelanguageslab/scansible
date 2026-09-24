from __future__ import annotations

from textwrap import dedent

from scansible.cst import YamlMap, YamlValue
from scansible.cst.constructor import CustomYAML


def parse_yaml_dict(yaml_content: str) -> dict[str, YamlValue]:
    """Parse a given YAML string to a dictionary."""
    loader = CustomYAML("test.yaml")
    result = loader.load(dedent(yaml_content))  # pyright: ignore[reportUnknownMemberType, reportAny]
    assert isinstance(result, YamlMap)
    return result  # pyright: ignore[reportUnknownVariableType]
