from __future__ import annotations

from typing import Collection, Mapping

import json
from collections import defaultdict

from .constants import COLLECTION_CONTENT_PATH
from .types import CollectionContent, ModuleInfo


def get_module_match_score(module: ModuleInfo, args: list[str]) -> int:
    extra_score = 0
    if module.collection.startswith('ansible.'):
        extra_score = 2
    elif module.collection.startswith('community.'):
        extra_score = 1

    return len(set(args) & set(module.params)) + extra_score

class CollectionIndex:
    collections: Mapping[str, CollectionContent]
    module_name_to_collections: Mapping[str, list[CollectionContent]]

    def __init__(self, collections: list[CollectionContent]) -> None:
        self.collections = {coll.name: coll for coll in collections}
        self.module_name_to_collections = defaultdict(list)

        for c in self.collections.values():
            for module_name in c.modules:
                self.module_name_to_collections[module_name].append(c)

    def get_candidate_modules(self, name: str) -> list[ModuleInfo]:
        colls = self.module_name_to_collections[name]
        return [c.modules[name] for c in colls]

    def get_module(self, name: str, args: Collection[str]) -> ModuleInfo | None:
        if '.' in name:
            [namespace, coll_name, module_name] = name.split('.')
            fqn = f'{namespace}.{coll_name}'
            try:
                return self.collections[fqn].modules[module_name]
            except KeyError:
                return None

        cands = self.get_candidate_modules(name)
        if not cands:
            return None
        if len(cands) == 1:
            return cands[0]

        return sorted(cands, reverse=True, key=lambda cand: get_module_match_score(cand, args))[0]


def get_collection_index() -> CollectionIndex:
    with COLLECTION_CONTENT_PATH.open('rt') as f:
        collection_content = json.load(f)

    collections: list[CollectionContent] = []
    for c in collection_content:
        name = c['name']
        namespace = c['namespace']
        fqn = f'{namespace}.{name}'
        modules: list[ModuleInfo] = []

        for content in c['contents']:
            match content:
                case {"name": cname, "type": "module", "parameters": cparams}:
                    simple_name = cname.removeprefix(f'{fqn}.')
                    all_params: list[str] = []
                    for p in cparams:
                        all_params.append(p['name'])
                        all_params.extend(p['aliases'])
                    modules.append(ModuleInfo(simple_name, fqn, all_params))
                case _: pass

        collections.append(CollectionContent(fqn, {mod.name: mod for mod in modules}))

    return CollectionIndex(collections)
