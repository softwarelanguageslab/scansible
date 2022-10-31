import yaml

AnsiblePosition = tuple[str, int, int]

class AnsibleBaseYAMLObject:
    ansible_pos: AnsiblePosition = ...

class AnsibleMapping(AnsibleBaseYAMLObject, dict[str | int | float | bool, AnsibleBaseYAMLObject]): ...

class AnsibleUnicode(AnsibleBaseYAMLObject, str): ...

class AnsibleSequence(AnsibleBaseYAMLObject, list[AnsibleBaseYAMLObject]): ...

class AnsibleVaultEncryptedUnicode(yaml.YAMLObject, AnsibleBaseYAMLObject):
    _ciphertext: bytes
