from __future__ import annotations

from textwrap import dedent

from scansible.representations.cst import YamlMap, YamlValue
from scansible.representations.cst.constructor import CustomYAML


def parse_yaml_dict(yaml_content: str) -> dict[str, YamlValue]:
    """Parse a given YAML string to a dictionary."""
    loader = CustomYAML("test.yaml")
    result = loader.load(dedent(yaml_content))  # pyright: ignore[reportUnknownMemberType, reportAny]
    assert isinstance(result, YamlMap)
    return result  # pyright: ignore[reportUnknownVariableType]
