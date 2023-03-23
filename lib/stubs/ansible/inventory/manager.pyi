from __future__ import annotations

from typing import Optional

from ansible.parsing.dataloader import DataLoader

class InventoryManager:
    def __init__(self, loader: DataLoader, sources: Optional[object] = ...) -> None: ...
