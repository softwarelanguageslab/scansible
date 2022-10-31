from typing import overload

from collections.abc import Mapping, Sequence, Iterator

import yaml

AnsiblePosition = tuple[str, int, int]

class AnsibleBaseYAMLObject:
    ansible_pos: AnsiblePosition = ...

class AnsibleMapping(AnsibleBaseYAMLObject, Mapping[str | int | float | bool, AnsibleBaseYAMLObject]):
    def __getitem__(self, key: str | int | float | bool) -> AnsibleBaseYAMLObject: ...
    def __len__(self) -> int: ...
    def __iter__(self) -> Iterator[str | int | float | bool]: ...

class AnsibleUnicode(AnsibleBaseYAMLObject, str): ...

class AnsibleSequence(AnsibleBaseYAMLObject, Sequence[AnsibleBaseYAMLObject]):
    @overload
    def __getitem__(self, idx: int) -> AnsibleBaseYAMLObject: ...
    @overload
    def __getitem__(self, idx: slice) -> Sequence[AnsibleBaseYAMLObject]: ...
    def __len__(self) -> int: ...

class AnsibleVaultEncryptedUnicode(yaml.YAMLObject, AnsibleBaseYAMLObject):
    _ciphertext: bytes
