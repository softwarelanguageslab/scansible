from __future__ import annotations

from typing import Any

from collections.abc import Callable

DEFAULT_TYPE_VALIDATORS: dict[str, Callable[[Any], Any]] = ...
