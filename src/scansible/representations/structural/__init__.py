"""Structural model representation for Ansible roles and playbooks."""

from __future__ import annotations

from . import extractor as extractor
from .extractor import extract_playbook as extract_playbook
from .extractor import extract_role as extract_role
from .representation import *
