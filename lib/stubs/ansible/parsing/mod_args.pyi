from __future__ import annotations

from typing import Any

class ModuleArgsParser:
    def __init__(self, ds: Any) -> None: ...
    def parse(self, skip_action_validation: bool = ...) -> tuple[str, object, str]: ...
