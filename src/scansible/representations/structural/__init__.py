"""Structural model representation for Ansible roles and playbooks."""

from .representation import *
from . import extractor
from .extractor import extract_role, extract_playbook
