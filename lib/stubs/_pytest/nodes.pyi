from typing import Any, List

class Node:
    ...

class Item(Node):
    _nodeid: str

    @property
    def nodeid(self) -> str: ...

    @property
    def keywords(self) -> List[str]: ...

    def add_marker(self, marker: Any) -> None: ...

    def get_closest_marker(self, name: str) -> Any: ...
