"""Utilities to work with Ansible entrypoints."""

from __future__ import annotations

from typing import Literal

import os
from collections.abc import Iterable
from contextlib import redirect_stderr
from pathlib import Path

from ansible.errors import AnsibleError
from ansible.parsing.dataloader import DataLoader


def is_entrypoint(path: Path) -> bool:
    """Check whether a file or directory is an Ansible entrypoint.

    If `path` is a directory and this returns True, then the entrypoint is a
    role. If `path` is a file and this returns True, then the entrypoint is a
    playbook."""

    # Hidden files or directories are unlikely to be entrypoints.
    if path.name.startswith('.'):
        return False

    if 'test' in path.name.lower() or 'molecule' in path.name.lower():
        return False

    if path.is_dir():
        # Quickly check whether this could be a role based on the child
        # directories.

        # Must have a tasks/main.yml or tasks/main.yaml file, otherwise nothing
        # to execute.
        return (path / 'tasks' / 'main.yaml').is_file() or (path / 'tasks' / 'main.yml').is_file()

    # Ansible entrypoints are generally YAML files. JSON is possible, but
    # extraordinarily improbable. Some files have no extension but are still
    # YAML, however, those are mostly reserved for inventory variables.
    if path.suffix.lower() not in ('.yml', '.yaml'):
        return False

    # Top-level content of every playbook needs to be a sequence of plays or
    # playbook imports. Plays require a "hosts" directive.
    # To quickly filter out definite non-playbooks without attempting to parse,
    # we'll read the content of the file and check whether it contains "hosts"
    # or "import_playbook". If not, it's definitely not a (working) playbook.
    content = path.read_text(errors='ignore')
    if 'hosts' not in content and 'import_playbook' not in content:
        return False

    # Finally, parse the YAML and check in more detail
    try:
        with open(os.devnull, 'w') as devnull, redirect_stderr(devnull):
            yaml_obj = DataLoader().load(content)
    except AnsibleError:
        # If the file fails to parse, don't consider it an entrypoint.
        return False

    return (isinstance(yaml_obj, list)
            and all(isinstance(child, dict) for child in yaml_obj)
            and all('hosts' in child or 'import_playbook' in child for child in yaml_obj))


def find_entrypoints(root: Path) -> list[tuple[Path, Literal['role', 'playbook']]]:
    """Find all entrypoints in a directory and return their paths and types."""

    return list(_find_entrypoints(root.resolve()))

def _find_entrypoints(root: Path) -> Iterable[tuple[Path, Literal['role', 'playbook']]]:
    if root.is_symlink():
        return

    # Check current path.
    if is_entrypoint(root):
        yield root, 'playbook' if root.is_file() else 'role'

    if root.is_file() or root.name.startswith('.') or 'test' in root.name.lower() or 'molecule' in root.name.lower():
        return

    if root.is_dir():
        for child in root.iterdir():
            yield from _find_entrypoints(child)

