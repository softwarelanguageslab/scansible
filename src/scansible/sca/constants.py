from __future__ import annotations

import pkgutil
import sys
from pathlib import Path

import rich
from ansible import constants as C

CONSOLE = rich.console.Console(width=999)

_COLLECTION_SEARCH_PATHS = map(Path, C.COLLECTIONS_PATHS + sys.path)
COLLECTION_PATHS = [
    coll_path
    for search_path in _COLLECTION_SEARCH_PATHS
    if (coll_path := search_path / "ansible_collections").is_dir()
]

_ROOT = Path.home() / "Work" / "Research" / "IaC" / "AnsibleCollectionsEcosystem"
COLLECTION_CONTENT_PATH = Path("cache") / "collection_content.json"

MODULE_SCA_PATH = (
    _ROOT
    / "DependencyPatternMatcher"
    / "target"
    / "scala-3.3.1"
    / "matcher.DependencyPatternMatcher-assembly-0.1.0-SNAPSHOT.jar"
)

MODULE_SCA_PROJECT_TIMEOUT = 60 * 60 * 60  # 1 hour
MODULE_SCA_JAVA_MAX_HEAP_SIZE = "64G"


ANSIBLE_BUILTIN_IGNORES = {
    "systemd",
    "ssl",
    "syslog",
    "gssapi",
    "urllib3",
    "ansible",
    "locale",
}

PYTHON_BUILTINS = set(sys.builtin_module_names) | {
    pkg.name
    for pkg in pkgutil.iter_modules()
    if pkg.module_finder.path.startswith("/usr/local/Cellar/python@3.12/")
}

DEBIAN_NAME_MAPPINGS = {
    "docker": "docker.io",
    "python": "python3.12",
}

HTML_CLASS_SEVERITY = {
    "critical": "dark",
    "high": "danger",
    "medium": "warning",
    "low": "info",
    "unknown": "secondary",
}

ANSIBLE_TRIVIAL_MODULES = {
    "ansible.builtin.import_tasks",
    "ansible.builtin.include_tasks",
    "ansible.builtin.include_role",
    "ansible.builtin.include_vars",
    "ansible.builtin.set_fact",
}

ANSIBLE_ROLE_INCLUDE_MODULES = {
    "ansible.builtin.include_role",
    "ansible.builtin.import_role",
    "include_role",
    "import_role",
}
