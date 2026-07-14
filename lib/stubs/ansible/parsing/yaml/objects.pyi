from __future__ import annotations

import yaml
from ansible.playbook.base import Value

AnsiblePosition = tuple[str, int, int]

class AnsibleBaseYAMLObject:
    ansible_pos: AnsiblePosition = ...

class AnsibleMapping(AnsibleBaseYAMLObject, dict[str | int | float | bool, Value]): ...
class AnsibleUnicode(AnsibleBaseYAMLObject, str): ...
class AnsibleSequence(AnsibleBaseYAMLObject, list[Value]): ...

class AnsibleVaultEncryptedUnicode(yaml.YAMLObject, AnsibleBaseYAMLObject):
    _ciphertext: bytes
