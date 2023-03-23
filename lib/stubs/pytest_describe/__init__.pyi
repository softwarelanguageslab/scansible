from __future__ import annotations

from typing import Callable

def behaves_like(
    shared_behavior: Callable[[], None]
) -> Callable[[Callable[[], None]], None]: ...
