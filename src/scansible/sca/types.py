from __future__ import annotations

from typing import NamedTuple

from collections.abc import Collection, Mapping, Sequence


class ModuleInfo(NamedTuple):
    name: str
    collection: str
    params: Sequence[str]


class CollectionContent(NamedTuple):
    name: str
    modules: Mapping[str, ModuleInfo]


class CollectionUsage(NamedTuple):
    name: str
    modules: Sequence[ModuleUsage]


class ModuleUsage(NamedTuple):
    name: str
    usages: list[str]


class RoleUsage(NamedTuple):
    name: str
    usages: Sequence[str]
    used_collections: Collection[str]
    used_modules: Collection[str]


class ModuleDependency(NamedTuple):
    name: str
    type: str


class Vulnerability(NamedTuple):
    package_name: str
    id: str
    summary: str
    severity: str
    description: str


class ProjectDependencies(NamedTuple):
    collections: Sequence[CollectionUsage]
    roles: Sequence[RoleUsage]
    module_dependencies: Mapping[str, Sequence[ModuleDependency]]

    @property
    def modules(self) -> Sequence[ModuleUsage]:
        return [mod for coll in self.collections for mod in coll.modules]
