"""Concrete Syntax Tree (CST) representation for Ansible code.

The CST is essentially a parsed YAML document with custom subclasses for the data types,
enriched with source code position information.
"""

from __future__ import annotations

from typing import cast

from ruamel.yaml import YAML

from scansible.representations.cst.constructor import CustomYAML
from scansible.utils import ProjectPath

from .nodes import LineColumn as LineColumn
from .nodes import Position as Position
from .nodes import YamlBool as YamlBool
from .nodes import YamlDate as YamlDate
from .nodes import YamlDatetime as YamlDatetime
from .nodes import YamlFloat as YamlFloat
from .nodes import YamlInt as YamlInt
from .nodes import YamlMap as YamlMap
from .nodes import YamlNode as YamlNode
from .nodes import YamlNone as YamlNone
from .nodes import YamlSeq as YamlSeq
from .nodes import YamlStr as YamlStr
from .nodes import YamlUnsafeStr as YamlUnsafeStr
from .nodes import YamlValue
from .nodes import YamlVaultValue as YamlVaultValue


def parse_file(path: ProjectPath) -> YamlValue:
    """Parse a YAML file using Ansible's parser."""
    loader = CustomYAML(str(path.relative))
    with path.absolute.open("rt") as f:
        return cast(YamlValue, loader.load(f))  # pyright: ignore[reportUnknownMemberType]
