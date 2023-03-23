"""Structural model representation for Ansible roles and playbooks."""

from __future__ import annotations

from . import extractor
from .extractor import extract_playbook, extract_role
from .representation import *
