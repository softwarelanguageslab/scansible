"""Constant values used throughout Scansible."""

from __future__ import annotations

from pathlib import Path

# Ansible constants, replicated from ansible.constants.
ANSIBLE_HOME = Path.home() / ".ansible"
DEFAULT_ROLES_PATH = [
    ANSIBLE_HOME / "roles",
    Path("/") / "usr" / "share" / "ansible" / "roles",
    Path("/") / "etc" / "ansible" / "roles",
]
COLLECTIONS_PATHS = [
    ANSIBLE_HOME / "collections",
    Path("/") / "usr" / "share" / "ansible" / "collections",
]

BUILTIN_COLLECTION_NAMES = ["ansible.builtin", "ansible.legacy"]

YAML_EXTENSIONS = [".yml", ".yaml", ".json"]
