from __future__ import annotations

from ansible.parsing.yaml.objects import AnsibleMapping, AnsibleUnicode

from .definition import RoleDefinition

class RoleRequirement(RoleDefinition):
    @staticmethod
    def role_yaml_parse(role: AnsibleUnicode | AnsibleMapping) -> dict[str, str]: ...
