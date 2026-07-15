from __future__ import annotations

META = """
dependencies: []
galaxy_info:
    name: test
    author: test
    platforms:
        - name: Debian
          versions:
            - all
"""

TASKS = """
- file:
    path: hello
- apt:
    name: test
"""

BROKEN_TASKS = """
file:
    path: hello
apt:
    name: test
"""

DEFAULTS = """
a: 123
"""

ROLE_VARS = """
b: 456
"""

HANDLERS = """
- name: restart x
  service:
    name: test
"""
