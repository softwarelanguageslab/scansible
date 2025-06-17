from __future__ import annotations

import csv
import json
import subprocess
from collections import defaultdict
from collections.abc import Mapping, Sequence
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import overload

import ansible

from scansible.sca.constants import (
    ANSIBLE_BUILTIN_IGNORES,
    COLLECTION_PATHS,
    MODULE_SCA_JAVA_MAX_HEAP_SIZE,
    MODULE_SCA_PATH,
    MODULE_SCA_PROJECT_TIMEOUT,
    PYTHON_BUILTINS,
)
from scansible.sca.types import ModuleDependency


class Cache:
    def __init__(self) -> None:
        self._cache: dict[str, Mapping[str, Sequence[ModuleDependency]]] = {}
        self._cache_path = Path("cache") / "dep_cache.json"
        if self._cache_path.is_file():
            self._read_cache()

    def _read_cache(self) -> None:
        cache_text = self._cache_path.read_text()
        cache_data = json.loads(cache_text)
        self._cache = {}

        for coll, values in cache_data.items():
            dct: dict[str, Sequence[ModuleDependency]] = {}
            self._cache[coll] = dct
            for mod, deps in values.items():
                dct[mod] = [ModuleDependency(dep["name"], dep["type"]) for dep in deps]

    def _write_cache(self) -> None:
        cache_dct = {}
        for coll, values in self._cache.items():
            dct = {}
            cache_dct[coll] = dct
            for mod, deps in values.items():
                dct[mod] = [{"name": dep.name, "type": dep.type} for dep in deps]

        old_cache = self._cache
        self._cache_path.write_text(json.dumps(cache_dct))
        self._read_cache()
        assert old_cache == self._cache

    def __contains__(self, key: str) -> bool:
        return key in self._cache

    def set(self, key: str, value: Mapping[str, Sequence[ModuleDependency]]) -> None:
        self._cache[key] = value
        self._write_cache()

    @overload
    def get(self, key: str) -> Mapping[str, Sequence[ModuleDependency]] | None: ...

    @overload
    def get(
        self, key: str, default: Mapping[str, Sequence[ModuleDependency]]
    ) -> Mapping[str, Sequence[ModuleDependency]]: ...

    def get(
        self, key: str, default: Mapping[str, Sequence[ModuleDependency]] | None = None
    ) -> Mapping[str, Sequence[ModuleDependency]] | None:
        return self._cache.get(key, default)


# Cache of collection name to module name to module dependencies
CACHE = Cache()


class CollectionNotFound(Exception):
    pass


def _prepare_input(coll_fqn: str, d: Path) -> Path:
    input_file = d / "input.json"

    if coll_fqn == "ansible.builtin":
        coll_path = Path(ansible.__file__).parent
        base_path = "ansible"
    else:
        [coll_namespace, coll_name] = coll_fqn.split(".")

        coll_path, base_path = _find_collection(coll_namespace, coll_name)

    coll_repr = {
        "projectId": coll_fqn,
        "projectPath": str(coll_path),
        "basePath": str(base_path),
    }
    input_file.write_text(json.dumps([coll_repr]))
    return input_file


def _find_collection(namespace: str, name: str) -> tuple[Path, Path]:
    for collections_path in COLLECTION_PATHS:
        coll_path = collections_path / namespace / name
        if coll_path.is_dir():
            break
    else:
        raise CollectionNotFound()

    base_path = Path("ansible_collections") / namespace / name / "plugins"

    return coll_path / "plugins", base_path


def extract_module_dependencies(module: str) -> Sequence[ModuleDependency]:
    [coll_namespace, coll_name, mod_name] = module.split(".")
    coll_fqn = f"{coll_namespace}.{coll_name}"

    if coll_fqn not in CACHE:
        coll_results = _extract_collection_dependencies(coll_fqn)
        CACHE.set(coll_fqn, coll_results)

    return CACHE.get(coll_fqn, {}).get(mod_name, [])


def _extract_collection_dependencies(
    coll_fqn: str,
) -> Mapping[str, Sequence[ModuleDependency]]:
    with TemporaryDirectory() as tmpd:
        d = Path(tmpd)

        try:
            input_file = _prepare_input(coll_fqn, d)
        except CollectionNotFound:
            print(f"Collection {coll_fqn} not in dataset!")
            return {}

        output_file = d / "output.csv"

        print(f"Processing {coll_fqn}")
        try:
            completed_proc = subprocess.run(
                [
                    "java",
                    f"-Xmx{MODULE_SCA_JAVA_MAX_HEAP_SIZE}",
                    "-jar",
                    str(MODULE_SCA_PATH),
                    str(input_file),
                    str(output_file),
                ],
                cwd=d,
                capture_output=True,
                text=True,
                timeout=MODULE_SCA_PROJECT_TIMEOUT,
            )
            completed_proc.check_returncode()
        except subprocess.CalledProcessError:
            print(f"{coll_fqn} failed!")
            print(completed_proc.stderr)
            return {}
        except subprocess.TimeoutExpired:
            print(f"{coll_fqn} timed out!")
            return {}

        return _parse_output(output_file)


def _parse_output(output_file: Path) -> Mapping[str, Sequence[ModuleDependency]]:
    with output_file.open() as outf:
        reader = csv.reader(outf)
        # Skip header
        contents = list(reader)[1:]

    output: dict[str, list[ModuleDependency]] = defaultdict(list)
    for row in contents:
        [coll_name, mod_path, dep_name, pattern] = row
        if not mod_path.startswith("modules/"):
            continue

        mod_name = mod_path.removeprefix("modules/")
        if pattern in ("GuardedImport", "CommunityGeneralDeps", "DynamicImport"):
            dep_type = "Python"
        elif pattern in ("GetBinPath", "CommunityGeneralCmdRunner"):
            dep_type = "OS"
        else:
            raise ValueError(f"Unknown pattern: {pattern}")

        if coll_name == "ansible.builtin" and dep_name in ANSIBLE_BUILTIN_IGNORES:
            continue
        if dep_type == "Python" and dep_name in PYTHON_BUILTINS:
            continue

        output[mod_name].append(ModuleDependency(dep_name, dep_type))

    return output
