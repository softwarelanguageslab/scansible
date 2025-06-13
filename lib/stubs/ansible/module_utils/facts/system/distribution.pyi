from __future__ import annotations

from collections.abc import Mapping, Sequence

class Distribution:
    OS_FAMILY_MAP: Mapping[str, Sequence[str]]
    OS_FAMILY: Mapping[str, str]
