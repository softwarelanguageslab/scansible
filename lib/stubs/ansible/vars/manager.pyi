from typing import Any, Optional

from ansible.parsing.dataloader import DataLoader

class VariableManager:
    def __init__(self, loader: Optional[DataLoader] = ..., inventory: Optional[Any] = ..., version_info: Optional[Any] = ...) -> None: ...