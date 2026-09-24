# pyright: reportAny = false, reportExplicitAny = false

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape

from scansible.sca.constants import HTML_CLASS_SEVERITY

if TYPE_CHECKING:
    from scansible.checks.base import Finding
    from scansible.pdg.representation import NodeLocation

    from .types import ProjectDependencies, Vulnerability


def _build_collections(dependencies: ProjectDependencies) -> list[dict[str, Any]]:
    return [
        {
            "name": coll.name,
            "modules": [
                mod._asdict()
                | {
                    "num_usages": len(mod.usages),
                    "dependencies": dependencies.module_dependencies.get(mod.name, []),
                }
                for mod in coll.modules
            ],
            "num_modules": len(coll.modules),
            "num_usages": sum(len(mod.usages) for mod in coll.modules),
        }
        for coll in dependencies.collections
    ]


def _build_module_dependencies(
    dependencies: ProjectDependencies,
    dependency_vulnerabilities: dict[str, list[Vulnerability]],
) -> dict[str, dict[str, Any]]:
    all_module_dependencies: dict[str, dict[str, Any]] = {}
    for mod, deps in dependencies.module_dependencies.items():
        for dep in deps:
            if dep.name not in all_module_dependencies:
                all_module_dependencies[dep.name] = {
                    "name": dep.name,
                    "type": dep.type,
                    "num_usages": 0,
                    "modules": [],
                }
            all_module_dependencies[dep.name]["num_usages"] += 1
            all_module_dependencies[dep.name]["modules"].append(mod)
    for dep in all_module_dependencies.values():
        dep["vulnerabilities"] = [
            vuln._asdict() for vuln in dependency_vulnerabilities[dep["name"]]
        ]
        for vuln in dep["vulnerabilities"]:
            vuln["severity_class"] = HTML_CLASS_SEVERITY.get(
                vuln["severity"], "secondary"
            )
            if vuln["severity"] not in HTML_CLASS_SEVERITY:
                vuln["severity"] = "unknown"
    return all_module_dependencies


def _build_vulnerabilities(
    dependency_vulnerabilities: dict[str, list[Vulnerability]],
) -> list[dict[str, str]]:
    vulnerabilities: list[dict[str, str]] = []
    for vulns in dependency_vulnerabilities.values():
        vulnerabilities.extend(vuln._asdict() for vuln in vulns)
    for vuln in vulnerabilities:
        if vuln["severity"] not in HTML_CLASS_SEVERITY:
            vuln["severity"] = "unknown"
    return vulnerabilities


def _build_pages() -> list[tuple[str, str]]:
    pages = [("index", "Dashboard")]
    pages.extend(
        (page_name, page_name.title())
        for page_name in (
            "collections",
            "roles",
            "modules",
            "dependencies",
            "weaknesses",
        )
    )
    return pages


def _build_smells(smells_raw: list[Finding]) -> list[dict[str, Any]]:
    smells: list[dict[str, Any]] = []
    for smell in smells_raw:
        sm: dict[str, Any] = {
            "code": smell.code,
            "summary": smell.summary,
            "explanation": smell.explanation,
            "location": smell.location,
            "hint_location": smell.hint_location,
            "hint_text": smell.hint_text,
        }
        sm["text"], sm["text_start"], sm["text_line"] = _read_code(smell.location, 5)
        if smell.hint_location is not None:
            sm["hint_code_text"], sm["hint_code_start"], sm["hint_code_line"] = (
                _read_code(smell.hint_location, 5)
            )
        smells.append(sm)
    return smells


def generate_report(
    project_name: str,
    output_dir: Path,
    dependencies: ProjectDependencies,
    dependency_vulnerabilities: dict[str, list[Vulnerability]],
    smells_raw: list[Finding],
) -> None:
    collections = _build_collections(dependencies)
    modules = [mod for coll in collections for mod in coll["modules"]]
    all_module_dependencies = _build_module_dependencies(
        dependencies, dependency_vulnerabilities
    )
    vulnerabilities = _build_vulnerabilities(dependency_vulnerabilities)
    pages = _build_pages()
    smells = _build_smells(smells_raw)

    env = Environment(
        loader=FileSystemLoader("src/scansible/sca/html"),
        autoescape=select_autoescape(),
    )
    env.globals = {  # pyright: ignore[reportAttributeAccessIssue]
        "project_name": project_name,
        "collections": collections,
        "modules": modules,
        "roles": dependencies.roles,
        "dependencies": list(all_module_dependencies.values()),
        "vulnerabilities": vulnerabilities,
        "smells": smells,
        "pages": pages,
    }

    for html_file, _ in pages:
        template = env.get_template(f"{html_file}.html.j2")
        content = template.render(current_file=html_file)
        _ = (output_dir / f"{html_file}.html").write_text(content)


def _read_code(loc: NodeLocation, num_lines: int) -> tuple[str, int, int]:
    if loc.is_synthetic:
        return "NOT FOUND!", 0, 0

    lineno = loc.start.line - 1
    file_path = Path(loc.path)
    try:
        text = file_path.read_text()
    except OSError:
        return "NOT FOUND!", 0, 0

    lines = text.splitlines()
    line_start = max(0, lineno - num_lines)
    line_end = min(len(lines) - 1, lineno + num_lines)

    return "\n".join(lines[line_start : line_end + 1]), line_start, lineno + 1
