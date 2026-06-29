"""Common types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date

#: Scalar values.
type ScalarValue = str | int | bool | float | date | None
#: Scalar or (possibly recursive) composite values.
type AnyValue = ScalarValue | Sequence[AnyValue] | Mapping[ScalarValue, AnyValue]
#: Possibly-recursive composite values.
type CompositeValue = Sequence[AnyValue] | Mapping[ScalarValue, AnyValue]
