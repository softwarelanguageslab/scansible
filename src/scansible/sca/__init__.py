from __future__ import annotations

import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Sequence

import attrs
from ansible import constants as ans_constants
from loguru import logger
from rich.markup import escape

from scansible.checks.security import run_all_checks
from scansible.checks.security.rules.base import RuleResult
from scansible.representations.pdg.extractor.main import extract_pdg
from scansible.representations.structural.extractor import (
    ExtractionContext,
    extract_playbook_file,
    extract_tasks_file,
)
from scansible.representations.structural.helpers import ProjectPath
from scansible.representations.structural.representation import (
    Block,
    Play,
    Playbook,
    Position,
    TaskFile,
)
from scansible.representations.structural.representation import TaskBase as Task
from scansible.sca.constants import (
    ANSIBLE_ROLE_INCLUDE_MODULES,
    ANSIBLE_TRIVIAL_MODULES,
    CONSOLE,
)
from scansible.utils.entrypoints import find_entrypoints

from .collection_info import ModuleInfo, get_collection_index
from .module_scanner import extract_module_dependencies
from .report import generate_report
from .types import CollectionUsage, ModuleUsage, ProjectDependencies, RoleUsage
from .vulnerabilities import find_vulnerabilities


def _find_role(name: str) -> Path | None:
    for root in ans_constants.DEFAULT_ROLES_PATH:
        p = Path(root) / name
        if Path(root) in p.resolve().parents:
            if p.is_dir():
                return p

    return None


def _extend_role_usages(
    role_path: Path, r: RoleUsage, module_usages: list[ModuleUsage]
) -> None:
    role_modules = extract_modules(role_path, False)

    for mod in role_modules:
        existing_mod = next(
            (mod_use for mod_use in module_usages if mod_use.name == mod.name), None
        )
        if existing_mod is None:
            module_usages.append(mod)
        else:
            existing_mod.usages.extend(mod.usages)

        mod_coll_namespace, mod_coll_name, _ = mod.name.split(".")
        mod_coll = f"{mod_coll_namespace}.{mod_coll_name}"
        r.used_collections.add(mod_coll)
        r.used_modules.add(mod.name)


def extract_dependencies(project: Path, output_path: Path) -> None:
    deps = _extract_project_dependencies(project)

    output_path.write_text(json.dumps(attrs.asdict(deps)))
    _print_dependencies(deps)


def _extract_project_dependencies(project: Path) -> ProjectDependencies:
    module_usages = extract_modules(project)
    role_usages = extract_roles(project)

    ru_todo = list(role_usages)

    while ru_todo:
        r = ru_todo.pop()
        role_path = _find_role(r.name)
        if role_path is None:
            logger.error(f"Could not resolve role {r.name}")
            continue

        _extend_role_usages(role_path, r, module_usages)
        new_ru = extract_roles(role_path, False)
        for ru in new_ru:
            ex_ru = next((ru2 for ru2 in role_usages if ru.name == ru2.name), None)
            if ex_ru is None:
                role_usages.append(ru)
                ru_todo.append(ru)

    collections: dict[str, list[ModuleUsage]] = defaultdict(list)
    for mod in module_usages:
        coll_fqn = ".".join(mod.name.split(".")[:2])
        collections[coll_fqn].append(mod)
    collection_usages = [
        CollectionUsage(name, mods) for name, mods in collections.items()
    ]

    dependencies = {
        module.name: extract_module_dependencies(module.name)
        for module in module_usages
    }

    return ProjectDependencies(collection_usages, role_usages, dependencies)


def _print_dependencies(project_deps: ProjectDependencies) -> None:
    for usage in sorted(
        project_deps.modules, key=lambda x: len(x.usages), reverse=True
    ):
        CONSOLE.print(f"[bold green]{usage.name}")
        for deps in sorted(
            project_deps.module_dependencies[usage.name], key=lambda dep: dep.name
        ):
            CONSOLE.print(
                f"\tDepends on: [bold]{deps.name}[/bold] {deps.type} {'package' if deps.type == 'Python' else 'binary'}"
            )
        for loc in usage.usages:
            CONSOLE.print(f"\t[blue]{loc}")


def scan_project(
    project: Path, output_dir: Path, role_search_paths: list[Path]
) -> None:
    smells = _detect_smells(project, role_search_paths)
    CONSOLE.print(smells)

    project_deps = _extract_project_dependencies(project)

    unique_dependencies: set[tuple[str, str]] = set()
    for deps in project_deps.module_dependencies.values():
        for dep in deps:
            unique_dependencies.add((dep.name, dep.type))

    dep_vulns = {
        dep_name: find_vulnerabilities(dep_name, dep_type)
        for dep_name, dep_type in unique_dependencies
    }

    _print_dependencies(project_deps)

    CONSOLE.print("")
    CONSOLE.print("[bold]Dependencies")
    for dep_name, vulns in sorted(dep_vulns.items()):
        cves = [vuln for vuln in vulns if vuln.id.startswith("CVE")]
        if cves:
            CONSOLE.print(
                f"{dep_name}: Possibly affected by {len(cves)} CVEs. Most recent:"
            )
        else:
            CONSOLE.print(f"{dep_name}: No known CVEs.")
        for cve in sorted(cves, key=lambda x: x.id, reverse=True)[:5]:
            CONSOLE.print(
                f"\t[bold red]{cve.id}[/bold red] (severity: {cve.severity}): {escape((cve.summary or cve.description).split('\n')[0])}"
            )

    output_dir.mkdir(exist_ok=True, parents=True)
    generate_report(
        project.name,
        output_dir,
        project_deps,
        dep_vulns,
        smells,
    )

    # json_results = _serialise_results_to_json(module_usages, dependencies, dep_vulns)


def _detect_smells(project: Path, role_search_paths: list[Path]) -> list[RuleResult]:
    cache_file = Path("cache") / "smells_cache.json"
    if not cache_file.is_file():
        cache_file.write_text(json.dumps({}))

    cache = json.loads(cache_file.read_text())

    if str(project) not in cache:
        smells = set(_detect_smells_uncached(project, role_search_paths))
        cache[str(project)] = list(smells)
        cache_file.write_text(json.dumps(cache))
        return list(smells)

    smells_raw = cache[str(project)]
    return [RuleResult(*smell) for smell in smells_raw]


def _detect_smells_uncached(
    project: Path, role_search_paths: list[Path]
) -> Iterable[RuleResult]:
    role_search_paths = role_search_paths + list(
        map(Path, ans_constants.DEFAULT_ROLES_PATH)
    )

    entrypoints = find_entrypoints(project)
    logger.remove()
    logger.add(CONSOLE.print, level="ERROR")

    for entrypoint, project_type in entrypoints:
        as_pb = project_type == "playbook"
        ctx = extract_pdg(
            entrypoint,
            "",
            "",
            role_search_paths,
            as_pb=as_pb,
        )

        CONSOLE.print(f"Running checks on {project_type} {entrypoint}")
        yield from run_all_checks(
            ctx.graph,
            os.getenv("DB_HOST"),
        )


def is_trivial_module(m: ModuleInfo) -> bool:
    mname = f"{m.collection}.{m.name}"

    return mname in ANSIBLE_TRIVIAL_MODULES


def extract_roles(project: Path, relative_paths: bool = True) -> list[RoleUsage]:
    first_party_roles = {
        path.name for path, etype in find_entrypoints(project) if etype == "role"
    }
    all_role_includes = list(_extract_role_includes(project))

    third_party_roles = {
        (r, loc) for r, loc in all_role_includes if r not in first_party_roles
    }

    role_to_usage: dict[str, list[str]] = defaultdict(list)
    for r, loc in third_party_roles:
        role_to_usage[r].append(":".join(map(str, loc)))

    if relative_paths:
        return [
            RoleUsage(
                r, [str(Path(loc).relative_to(project)) for loc in locs], set(), set()
            )
            for r, locs in role_to_usage.items()
        ]
    else:
        return [RoleUsage(r, locs, set(), set()) for r, locs in role_to_usage.items()]


def _extract_role_includes(project: Path) -> Iterable[tuple[str, Position]]:
    all_yaml_files = list(find_all_yaml_files(project))

    worklist: list[Play | Task] = []
    for f in all_yaml_files:
        rep = try_extract_pb_or_tasks_file(f)
        if rep is None:
            continue

        match rep:
            case Playbook(_):
                worklist.extend(rep.plays)
            case TaskFile(_):
                worklist.extend(flatten_tasks(rep.tasks))

    while worklist:
        item = worklist.pop()
        match item:
            case Play(_):
                worklist.extend(flatten_tasks(item.pre_tasks))
                worklist.extend(flatten_tasks(item.tasks))
                worklist.extend(flatten_tasks(item.post_tasks))
                worklist.extend(flatten_tasks(item.handlers))

                for r in item.roles:
                    yield r.role, item.location

            case Task(_):
                if item.action in ANSIBLE_ROLE_INCLUDE_MODULES:
                    yield str(item.args["name"]), item.location


def extract_modules(project: Path, relative_paths: bool = True) -> list[ModuleUsage]:
    all_tasks = extract_all_tasks(project)
    collection_index = get_collection_index()
    modules = [
        (task, collection_index.get_module(task.action, task.args.keys()))
        for task in all_tasks
    ]

    usages: dict[str, list[str]] = defaultdict(list)
    for t, m in modules:
        if m is None:
            continue
        if is_trivial_module(m):
            continue
        mname = f"{m.collection}.{m.name}"
        tloc = f"{t.location[0]}:{t.location[1]}"
        usages[mname].append(tloc)

    if relative_paths:
        return [
            ModuleUsage(name, [str(Path(loc).relative_to(project)) for loc in locs])
            for name, locs in usages.items()
        ]
    else:
        return [ModuleUsage(name, locs) for name, locs in usages.items()]


def extract_all_tasks(project: Path) -> list[Task]:
    all_yaml_files = list(find_all_yaml_files(project))

    tasks: list[Task] = []
    for f in all_yaml_files:
        rep = try_extract_pb_or_tasks_file(f)
        if rep is None:
            continue

        match rep:
            case Playbook(_):
                for p in rep.plays:
                    tasks.extend(flatten_tasks(p.pre_tasks))
                    tasks.extend(flatten_tasks(p.tasks))
                    tasks.extend(flatten_tasks(p.post_tasks))
                    tasks.extend(flatten_tasks(p.handlers))
            case TaskFile(_):
                tasks.extend(flatten_tasks(rep.tasks))

    return tasks


def flatten_tasks(ts: Sequence[Task | Block]) -> Iterable[Task]:
    for t in ts:
        match t:
            case Task(_):
                yield t
            case Block(_):
                yield from flatten_tasks(t.block)
                yield from flatten_tasks(t.rescue)
                yield from flatten_tasks(t.always)


def try_extract_pb_or_tasks_file(f: Path) -> Playbook | TaskFile | None:
    try:
        return extract_tasks_file(ProjectPath.from_root(f), ExtractionContext(False))
    except:
        try:
            return extract_playbook_file(ProjectPath.from_root(f), False)[0]
        except:
            return None


def find_all_yaml_files(project: Path) -> Iterable[Path]:
    for d, _, files in project.walk():
        for f in files:
            p = d / f
            if (
                p.is_file()
                and p.suffix.lower() in (".yaml", ".yml")
                and not _is_test_file(p)
            ):
                yield p


def _is_test_file(p: Path) -> bool:
    return any(token in p.parts for token in ("test", "tests", "molecule"))
