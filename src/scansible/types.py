"""Common types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, datetime

from pydantic import BaseModel


class VaultValue(BaseModel, frozen=True):
    """Represents an Ansible encrypted vault value."""

    #: The encrypted data.
    data: bytes
    #: The source code location
    ansible_pos: tuple[str, int, int]


#: Scalar values.
type ScalarValue = str | int | bool | float | date | datetime | VaultValue | None
#: Scalar or (possibly recursive) composite values.
type AnyValue = ScalarValue | Sequence[AnyValue] | Mapping[ScalarValue, AnyValue]
#: Possibly-recursive composite values.
type CompositeValue = Sequence[AnyValue] | Mapping[ScalarValue, AnyValue]
