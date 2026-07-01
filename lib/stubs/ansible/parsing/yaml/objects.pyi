from __future__ import annotations

import yaml

from scansible.representations.structural.ansible_types import AnsibleValue

AnsiblePosition = tuple[str, int, int]

class AnsibleBaseYAMLObject:
    ansible_pos: AnsiblePosition = ...

class AnsibleMapping(
    AnsibleBaseYAMLObject, dict[str | int | float | bool, AnsibleValue]
): ...
class AnsibleUnicode(AnsibleBaseYAMLObject, str): ...
class AnsibleSequence(AnsibleBaseYAMLObject, list[AnsibleValue]): ...

class AnsibleVaultEncryptedUnicode(yaml.YAMLObject, AnsibleBaseYAMLObject):
    _ciphertext: bytes
