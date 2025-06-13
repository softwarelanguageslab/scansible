from __future__ import annotations

from typing import Any

from pathlib import Path

import attrs
from jinja2 import Environment, FileSystemLoader, select_autoescape

from scansible.checks.security.rules.base import RuleResult
from scansible.sca.constants import HTML_CLASS_SEVERITY

from .types import ModuleDependencies, ModuleUsage, RoleUsage, Vulnerability


def generate_report(project_name: str, output_dir: Path, raw_modules: list[ModuleUsage], role_usages: list[RoleUsage], module_dependencies: dict[str, ModuleDependencies], dependency_vulnerabilities: dict[str, list[Vulnerability]], smells_raw: list[RuleResult]) -> None:
    modules = [attrs.asdict(mod) | {'num_usages': len(mod.usages)} for mod in raw_modules]
    for mod in modules:
        deps = module_dependencies.get(mod['name'])
        mod['dependencies'] = deps.dependencies if deps is not None else []

    collections: dict[str, dict[str, Any]] = {}
    for module in modules:
        coll_fqn = '.'.join(module['name'].split('.')[:2])
        if coll_fqn not in collections:
            collections[coll_fqn] = {
                'name': coll_fqn,
                'modules': [],
                'num_modules': 0,
                'num_usages': 0,
            }
        coll_dct = collections[coll_fqn]
        coll_dct['num_modules'] += 1
        coll_dct['num_usages'] += len(module['usages'])
        coll_dct['modules'].append(module)

    dependencies: dict[str, dict[str, Any]] = {}
    for mod in module_dependencies.values():
        for dep in mod.dependencies:
            if dep.name not in dependencies:
                dependencies[dep.name] = {
                    'name': dep.name,
                    'type': dep.type,
                    'num_usages': 0,
                    'modules': [],
                }
            dependencies[dep.name]['num_usages'] += 1
            dependencies[dep.name]['modules'].append(mod.name)
    for dep in dependencies.values():
        dep['vulnerabilities'] = [attrs.asdict(vuln) for vuln in dependency_vulnerabilities[dep['name']]]
        for vuln in dep['vulnerabilities']:
            vuln['severity_class'] = HTML_CLASS_SEVERITY.get(vuln['severity'], 'secondary')
            if vuln['severity'] not in HTML_CLASS_SEVERITY:
                vuln['severity'] = 'unknown'

    vulnerabilities: list[Vulnerability] = []
    for vulns in dependency_vulnerabilities.values():
        vulnerabilities.extend(attrs.asdict(vuln) for vuln in vulns)
    for vuln in vulnerabilities:
        if vuln['severity'] not in HTML_CLASS_SEVERITY:
            vuln['severity'] = 'unknown'

    pages = [('index', 'Dashboard')]
    for page_name in ('collections', 'roles', 'modules', 'dependencies', 'weaknesses'):
        pages.append((page_name, page_name[0].upper() + page_name[1:]))

    smells: list[dict[str, Any]] = []
    for smell in smells_raw:
        sm = smell._asdict()
        sm['source_text'], sm['source_text_start'], sm['source_text_line'] = _read_code(smell.source_location, 5)
        sm['sink_text'], sm['sink_text_start'], sm['sink_text_line'] = _read_code(smell.sink_location, 5)
        smells.append(sm)

    env = Environment(
        loader=FileSystemLoader("src/scansible/sca/html"),
        autoescape=select_autoescape(),
    )
    env.globals = dict(
            project_name=project_name,
            collections=list(collections.values()),
            modules=modules,
            roles=role_usages,
            dependencies=list(dependencies.values()),
            vulnerabilities=vulnerabilities,
            smells=smells,
            pages=pages,
        )

    for html_file, _ in pages:
        template = env.get_template(f'{html_file}.html.j2')
        content = template.render(current_file=html_file)
        (output_dir / f'{html_file}.html').write_text(content)


def _read_code(loc: str, num_lines: int) -> tuple[str, int, int]:
    print(loc)
    *file_path_str, lineno_raw, _ = loc.split(':')
    lineno = int(lineno_raw) - 1
    file_path = Path(':'.join(file_path_str))
    try:
        text = file_path.read_text()
    except IOError:
        return 'NOT FOUND!', 0, 0

    lines = text.splitlines()
    line_start = max(0, lineno - num_lines)
    line_end = min(len(lines) - 1, lineno + num_lines)

    return '\n'.join(lines[line_start:line_end + 1]), line_start, lineno + 1
