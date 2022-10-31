from ansible.parsing.yaml.objects import AnsibleUnicode, AnsibleMapping

from .definition import RoleDefinition

class RoleRequirement(RoleDefinition):
    @staticmethod
    def role_yaml_parse(role: AnsibleUnicode | AnsibleMapping) -> dict[str, str]: ...
