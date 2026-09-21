from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Iterable, Sequence
from pathlib import Path

from loguru import logger
from pydantic import ValidationError
from rich.markup import escape
from ruamel.yaml import YAMLError

from scansible.checks.security import run_all_checks
from scansible.checks.security.rules.base import RuleResult
from scansible.constants import DEFAULT_ROLES_PATH
from scansible.representations.ast import BaseTask as Task
from scansible.representations.ast import (
    Block,
    ExtractionContext,
    HandlerBlock,
    Play,
    Playbook,
    StrLiteral,
    TaskFile,
)
from scansible.representations.pdg.builder.main import build_pdg
from scansible.sca.constants import (
    ANSIBLE_ROLE_INCLUDE_MODULES,
    ANSIBLE_TRIVIAL_MODULES,
    CONSOLE,
)
from scansible.utils import Position, ProjectPath
from scansible.utils.entrypoints import find_entrypoints

from .collection_info import get_collection_index
from .module_scanner import extract_module_dependencies
from .report import generate_report
from .types import (
    CollectionUsage,
    ModuleInfo,
    ModuleUsage,
    ProjectDependencies,
    RoleUsage,
)
from .vulnerabilities import find_vulnerabilities


def _find_role(name: str) -> Path | None:
    for root in DEFAULT_ROLES_PATH:
        p = Path(root) / name
        if Path(root) in p.resolve().parents and p.is_dir():
            return p

    return None


def _extend_role_usages(
    role_path: Path, r: RoleUsage, module_usages: list[ModuleUsage]
) -> None:
    role_modules = extract_modules(role_path, return_relative_paths=False)

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

    _ = output_path.write_text(json.dumps(deps._asdict()))
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
        new_ru = extract_roles(role_path, return_relative_paths=False)
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
    smells = list(_detect_smells(project, role_search_paths))
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
    generate_report(project.name, output_dir, project_deps, dep_vulns, smells)


def _detect_smells(
    project: Path, role_search_paths: list[Path]
) -> Iterable[RuleResult]:
    role_search_paths = role_search_paths + list(map(Path, DEFAULT_ROLES_PATH))

    entrypoints = find_entrypoints(project)
    logger.remove()
    _ = logger.add(CONSOLE.print, level="ERROR")

    for entrypoint, project_type in entrypoints:
        as_pb = project_type == "playbook"
        ctx = build_pdg(entrypoint, role_search_paths, as_pb=as_pb)

        CONSOLE.print(f"Running checks on {project_type} {entrypoint}")
        yield from run_all_checks(ctx.graph)


def is_trivial_module(m: ModuleInfo) -> bool:
    mname = f"{m.collection}.{m.name}"

    return mname in ANSIBLE_TRIVIAL_MODULES


def extract_roles(
    project: Path, *, return_relative_paths: bool = True
) -> list[RoleUsage]:
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

    if return_relative_paths:
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
            case Playbook():
                worklist.extend(p for p in rep.plays if isinstance(p, Play))
            case TaskFile():
                worklist.extend(flatten_tasks(rep.tasks))

    while worklist:
        item = worklist.pop()
        match item:
            case Play():
                worklist.extend(flatten_tasks(item.pre_tasks))
                worklist.extend(flatten_tasks(item.tasks))
                worklist.extend(flatten_tasks(item.post_tasks))
                worklist.extend(flatten_tasks(item.handlers))

                for r in item.roles:
                    yield r.role, item.position

            case Task():
                if item.action in ANSIBLE_ROLE_INCLUDE_MODULES:
                    yield str(item.args[StrLiteral("name")]), item.position


def extract_modules(
    project: Path, *, return_relative_paths: bool = True
) -> list[ModuleUsage]:
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
        tloc = f"{t.__position__.path}:{t.__position__.start.line}"
        usages[mname].append(tloc)

    if return_relative_paths:
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
            case Playbook():
                for p in rep.plays:
                    if not isinstance(p, Play):
                        continue
                    tasks.extend(flatten_tasks(p.pre_tasks))
                    tasks.extend(flatten_tasks(p.tasks))
                    tasks.extend(flatten_tasks(p.post_tasks))
                    tasks.extend(flatten_tasks(p.handlers))
            case TaskFile():
                tasks.extend(flatten_tasks(rep.tasks))

    return tasks


def flatten_tasks(ts: Sequence[Task | Block | HandlerBlock]) -> Iterable[Task]:
    for t in ts:
        match t:
            case Task():
                yield t
            case Block() | HandlerBlock():
                yield from flatten_tasks(t.block)
                yield from flatten_tasks(t.rescue)
                yield from flatten_tasks(t.always)


def try_extract_pb_or_tasks_file(f: Path) -> Playbook | TaskFile | None:
    ctx = ExtractionContext(lenient=False)
    try:
        return TaskFile.load(ProjectPath.from_root(f), ctx)
    except (ValidationError, YAMLError):
        try:
            return Playbook.load(ProjectPath.from_root(f), ctx)
        except (ValidationError, YAMLError):
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
