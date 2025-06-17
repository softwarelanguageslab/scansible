from __future__ import annotations

from typing import Mapping, Sequence

from attrs import define


@define
class ModuleInfo:
    name: str
    collection: str
    params: Sequence[str]


@define
class CollectionContent:
    name: str
    modules: Mapping[str, ModuleInfo]


@define
class CollectionUsage:
    name: str
    modules: Sequence[ModuleUsage]


@define
class ModuleUsage:
    name: str
    usages: list[str]


@define
class RoleUsage:
    name: str
    usages: Sequence[str]
    used_collections: set[str]
    used_modules: set[str]


@define
class ModuleDependency:
    name: str
    type: str


@define
class Vulnerability:
    package_name: str
    id: str
    summary: str
    severity: str
    description: str


@define
class ProjectDependencies:
    collections: list[CollectionUsage]
    roles: list[RoleUsage]
    module_dependencies: dict[str, Sequence[ModuleDependency]]

    @property
    def modules(self) -> list[ModuleUsage]:
        return [mod for coll in self.collections for mod in coll.modules]
