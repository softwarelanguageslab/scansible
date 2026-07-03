"""Common types."""

from __future__ import annotations

from typing import Annotated

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from ansible.parsing.yaml.objects import AnsibleVaultEncryptedUnicode
from pydantic import BaseModel, BeforeValidator


class VaultValue(BaseModel, frozen=True):
    """Represents an Ansible encrypted vault value."""

    #: The encrypted data.
    data: bytes
    #: The source code location
    ansible_pos: tuple[str, int, int]

    @classmethod
    def from_ansible_vault_value(
        cls, object: AnsibleVaultEncryptedUnicode
    ) -> VaultValue:
        return cls(data=object._ciphertext, ansible_pos=object.ansible_pos)


def _coerce_vault(obj: object) -> object:
    if isinstance(obj, AnsibleVaultEncryptedUnicode):
        return VaultValue.from_ansible_vault_value(obj)
    return obj


#: Scalar values.
type _ScalarValue = str | int | bool | float | date | datetime | VaultValue | None
#: Scalar values, with automated coercion of encrypted vault values to `VaultValue` representation.
type ScalarValue = Annotated[_ScalarValue, BeforeValidator(_coerce_vault)]

#: Scalar or (possibly recursive) composite values.
type AnyValue = ScalarValue | Sequence[AnyValue] | Mapping[ScalarValue, AnyValue]
#: Possibly-recursive composite values.
type CompositeValue = Sequence[AnyValue] | Mapping[ScalarValue, AnyValue]
