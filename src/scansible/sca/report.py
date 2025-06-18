from __future__ import annotations

from typing import Any

from pathlib import Path

import attrs
from jinja2 import Environment, FileSystemLoader, select_autoescape

from scansible.checks.security.rules.base import RuleResult
from scansible.sca.constants import HTML_CLASS_SEVERITY

from .types import ProjectDependencies, Vulnerability


def generate_report(
    project_name: str,
    output_dir: Path,
    dependencies: ProjectDependencies,
    dependency_vulnerabilities: dict[str, list[Vulnerability]],
    smells_raw: list[RuleResult],
) -> None:
    collections: list[dict[str, Any]] = []
    for coll in dependencies.collections:
        collections.append(
            {
                "name": coll.name,
                "modules": [
                    attrs.asdict(mod)
                    | {
                        "num_usages": len(mod.usages),
                        "dependencies": dependencies.module_dependencies.get(
                            mod.name, []
                        ),
                    }
                    for mod in coll.modules
                ],
                "num_modules": len(coll.modules),
                "num_usages": sum(len(mod.usages) for mod in coll.modules),
            }
        )

    modules = [mod for coll in collections for mod in coll["modules"]]

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
            attrs.asdict(vuln) for vuln in dependency_vulnerabilities[dep["name"]]
        ]
        for vuln in dep["vulnerabilities"]:
            vuln["severity_class"] = HTML_CLASS_SEVERITY.get(
                vuln["severity"], "secondary"
            )
            if vuln["severity"] not in HTML_CLASS_SEVERITY:
                vuln["severity"] = "unknown"

    vulnerabilities: list[dict[str, str]] = []
    for vulns in dependency_vulnerabilities.values():
        vulnerabilities.extend(attrs.asdict(vuln) for vuln in vulns)
    for vuln in vulnerabilities:
        if vuln["severity"] not in HTML_CLASS_SEVERITY:
            vuln["severity"] = "unknown"

    pages = [("index", "Dashboard")]
    for page_name in ("collections", "roles", "modules", "dependencies", "weaknesses"):
        pages.append((page_name, page_name[0].upper() + page_name[1:]))

    smells: list[dict[str, Any]] = []
    for smell in smells_raw:
        sm = smell._asdict()
        sm["source_text"], sm["source_text_start"], sm["source_text_line"] = _read_code(
            smell.source_location, 5
        )
        sm["sink_text"], sm["sink_text_start"], sm["sink_text_line"] = _read_code(
            smell.sink_location, 5
        )
        smells.append(sm)

    env = Environment(
        loader=FileSystemLoader("src/scansible/sca/html"),
        autoescape=select_autoescape(),
    )
    env.globals = dict(
        project_name=project_name,
        collections=collections,
        modules=modules,
        roles=dependencies.roles,
        dependencies=list(all_module_dependencies.values()),
        vulnerabilities=vulnerabilities,
        smells=smells,
        pages=pages,
    )

    for html_file, _ in pages:
        template = env.get_template(f"{html_file}.html.j2")
        content = template.render(current_file=html_file)
        (output_dir / f"{html_file}.html").write_text(content)


def _read_code(loc: str, num_lines: int) -> tuple[str, int, int]:
    *file_path_str, lineno_raw, _ = loc.split(":")
    lineno = int(lineno_raw) - 1
    file_path = Path(":".join(file_path_str))
    try:
        text = file_path.read_text()
    except IOError:
        return "NOT FOUND!", 0, 0

    lines = text.splitlines()
    line_start = max(0, lineno - num_lines)
    line_end = min(len(lines) - 1, lineno + num_lines)

    return "\n".join(lines[line_start : line_end + 1]), line_start, lineno + 1
