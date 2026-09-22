# pyright: reportAny = false, reportUnknownVariableType = false, reportUnknownMemberType = false, reportUnknownArgumentType = false, reportUnknownParameterType = false

"""Custom YAML object constructor.

This constructor creates objects while keeping track of their locations in the file.
"""

from __future__ import annotations

from typing import override

from collections.abc import Iterable
from datetime import date, datetime

from ruamel.yaml import YAML
from ruamel.yaml.constructor import SafeConstructor
from ruamel.yaml.nodes import Node
from ruamel.yaml.resolver import BaseResolver
from yaml.resolver import Resolver as _PyYAMLResolver

from scansible.utils import LineColumn, Location

from .nodes import (
    YamlBool,
    YamlDate,
    YamlDatetime,
    YamlFloat,
    YamlInt,
    YamlMap,
    YamlNode,
    YamlNone,
    YamlSeq,
    YamlStr,
    YamlUnsafeStr,
    YamlVaultValue,
)


class CustomConstructor(SafeConstructor):
    """Custom YAML object constructor that constructs the CST subclasses."""

    def __init__(
        self, *, preserve_quotes: bool | None = None, loader: YAML | None = None
    ) -> None:
        assert isinstance(loader, CustomYAML)
        super().__init__(preserve_quotes, loader)

    def _get_location(self, node: Node) -> Location:
        start = LineColumn.from_yaml_mark(node.start_mark)
        end = LineColumn.from_yaml_mark(node.end_mark)
        return Location(path=self.loader.current_file_name, start=start, end=end)

    @override
    def construct_yaml_str(self, node: Node) -> YamlStr:
        value = super().construct_yaml_str(node)
        obj = YamlStr(value, location=self._get_location(node))
        return obj

    @override
    def construct_yaml_int(self, node: Node) -> YamlInt:
        value = super().construct_yaml_int(node)
        obj = YamlInt(value, location=self._get_location(node))
        return obj

    @override
    def construct_yaml_float(self, node: Node) -> YamlFloat:
        value = super().construct_yaml_float(node)
        obj = YamlFloat(value, location=self._get_location(node))
        return obj

    @override
    def construct_yaml_bool(self, node: Node) -> YamlBool:  # pyright: ignore[reportIncompatibleMethodOverride]
        value = super().construct_yaml_bool(node)
        obj = YamlBool(value, location=self._get_location(node))
        return obj

    @override
    def construct_yaml_null(self, node: Node) -> YamlNone:
        super().construct_yaml_null(node)
        obj = YamlNone(location=self._get_location(node))
        return obj

    @override
    def construct_yaml_timestamp(self, node: Node, values: object = None) -> YamlNode:
        value = super().construct_yaml_timestamp(node, values)
        # `datetime` is a subclass of `date`, so it must be checked first.
        if isinstance(value, datetime):
            obj = YamlDatetime(value, location=self._get_location(node))
        else:
            assert isinstance(value, date)
            obj = YamlDate(value, location=self._get_location(node))
        return obj

    @override
    def construct_yaml_map(self, node: Node) -> Iterable[YamlMap]:  # pyright: ignore[reportMissingTypeArgument]
        data = YamlMap(location=self._get_location(node))
        yield data
        value = self.construct_mapping(node)
        data.update(value)

    @override
    def construct_yaml_seq(self, node: Node) -> Iterable[YamlSeq]:  # pyright: ignore[reportMissingTypeArgument]
        data = YamlSeq(location=self._get_location(node))
        yield data
        value = self.construct_sequence(node)
        data.extend(value)

    def construct_vault_value(self, node: Node) -> YamlVaultValue:
        value = self.construct_scalar(node)
        obj = YamlVaultValue(value, location=self._get_location(node))
        return obj

    def construct_unsafe_value(self, node: Node) -> YamlUnsafeStr:
        # FIXME: This is a modifier rather than a new data type, so maybe we should instead add an attribute
        # to each YamlNode indicating whether it's unsafe, and set the attribute for any contained value?
        # FIXME: This might also contain other data types?
        value = self.construct_scalar(node)
        obj = YamlUnsafeStr(value, location=self._get_location(node))
        return obj


CustomConstructor.add_constructor(
    "tag:yaml.org,2002:str", CustomConstructor.construct_yaml_str
)
CustomConstructor.add_constructor(
    "tag:yaml.org,2002:bool", CustomConstructor.construct_yaml_bool
)
CustomConstructor.add_constructor(
    "tag:yaml.org,2002:null", CustomConstructor.construct_yaml_null
)
CustomConstructor.add_constructor(
    "tag:yaml.org,2002:int", CustomConstructor.construct_yaml_int
)
CustomConstructor.add_constructor(
    "tag:yaml.org,2002:float", CustomConstructor.construct_yaml_float
)
CustomConstructor.add_constructor(
    "tag:yaml.org,2002:timestamp", CustomConstructor.construct_yaml_timestamp
)
CustomConstructor.add_constructor(
    "tag:yaml.org,2002:map", CustomConstructor.construct_yaml_map
)
CustomConstructor.add_constructor(
    "tag:yaml.org,2002:seq", CustomConstructor.construct_yaml_seq
)
CustomConstructor.add_constructor("!unsafe", CustomConstructor.construct_unsafe_value)
CustomConstructor.add_constructor("!vault", CustomConstructor.construct_vault_value)
CustomConstructor.add_constructor(
    "!vault-encrypted", CustomConstructor.construct_vault_value
)


class AnsibleResolver(BaseResolver):
    """Scalar tag resolver that matches Ansible's own YAML parsing.

    Ansible parses YAML using PyYAML's plain (not fully YAML-1.1-compliant)
    `Resolver`, not ruamel's YAML 1.2 or YAML-1.1-per-spec resolvers, and the
    differences are observable: e.g. Ansible does not treat bare `y`/`n` as
    booleans (only `yes`/`no`/`on`/`off`/`true`/`false`), and requires a signed
    exponent for scientific-notation floats (`1.5e+10`, not `1.5e10`)

    We'll reuse PyYAML's own resolver table directly, as this guarantees this matches Ansible
    exactly rather than approximating it by hand.
    """

    def __init__(
        self, version: object = None, loader: object = None, loadumper: object = None
    ) -> None:
        super().__init__(loader if loader is not None else loadumper)
        self.yaml_implicit_resolvers: dict[object, object] = dict(
            _PyYAMLResolver.yaml_implicit_resolvers
        )

    @property
    @override
    def processing_version(self) -> tuple[int, int]:
        return (1, 1)


class CustomYAML(YAML):
    """Custom YAML interface subclass.

    This is needed to store the file name of the file being loaded, which is accessed by the custom constructor.
    """

    current_file_name: str

    def __init__(
        self,
        file_name: str = "",
        *,
        typ: str | list[str] | None = None,
        pure: bool = False,
        output: object = None,
        plug_ins: object = None,
    ) -> None:
        super().__init__(typ=typ, pure=pure, output=output, plug_ins=plug_ins)
        self.current_file_name = file_name
        # The YAML parser raises on duplicate keys, Ansible warns but allows it, so ignore duplicate keys.
        # TODO: We should perhaps log keep track of duplicate keys and warn about it too.
        self.allow_duplicate_keys: bool = True
        self.Resolver: type[AnsibleResolver] = AnsibleResolver
        self.Constructor: type[CustomConstructor] = CustomConstructor
